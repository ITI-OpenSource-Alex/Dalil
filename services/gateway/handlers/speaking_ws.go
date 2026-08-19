package handlers

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	// fastws is the client half. gofiber/websocket/v2 wraps this same library for
	// the server side but re-exports only what a handler needs -- there is no
	// Dialer or CloseError on it -- so the upstream leg dials through the
	// underlying package. Both ends are therefore the same implementation, which
	// is why one relay loop can drive both.
	fastws "github.com/fasthttp/websocket"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/utils"
	"github.com/gofiber/websocket/v2"
	"github.com/rs/zerolog"
)

// wsConn is the slice of a WebSocket connection the relay needs. It exists
// because the two legs have different concrete types -- *websocket.Conn on the
// browser side, *fastws.Conn upstream -- and because it lets relay() be tested
// against an in-memory pair rather than only through a live socket.
type wsConn interface {
	ReadMessage() (int, []byte, error)
	WriteMessage(messageType int, data []byte) error
	SetReadDeadline(t time.Time) error
	SetWriteDeadline(t time.Time) error
	Close() error
}

// Locals keys the relay reads. They are set by Upgrade and read by Proxy, which
// runs after the *fiber.Ctx has been recycled -- so the values are copied, not
// referenced.
const (
	localsSpeakingUserID      = "speaking_ws_user_id"
	localsSpeakingCorrelation = "speaking_ws_correlation_id"
	localsSpeakingTraceparent = "speaking_ws_traceparent"
	localsSpeakingExamSession = "speaking_ws_exam_session_id"
	localsSpeakingExamMode    = "speaking_ws_exam_mode"
)

// speakingWSDeadline bounds a single blocked read or write on either leg.
//
// It is a liveness guard, not a session budget: it is refreshed on every frame,
// so a healthy session of any length survives while a wedged one is reaped. A
// fixed session-length deadline would kill every conversation at the same
// second regardless of health, and GOA-032's own e2e SLO is 90s -- longer than
// any value that would be safe as a hard cap.
const speakingWSDeadline = 3 * time.Minute

// SpeakingWSHandler reverse-proxies the browser's WebSocket to the Speaking
// service, so a speaking session picks up JWT validation, rate limiting and a
// correlation ID like every other route (GOA-132, the last of BUG-029's four
// flows).
//
// This is deliberately NOT modelled on StreamHandler. That proxies a half-duplex
// HTTP body: one upstream response copied to one client, ending when the body
// ends. A WebSocket is full-duplex and either side may close first, so the relay
// is two independent copy loops with a shared shutdown -- a different problem
// wearing similar clothes.
type SpeakingWSHandler struct {
	upstreamWSURL string
	dialer        *fastws.Dialer
	logger        zerolog.Logger
}

// NewSpeakingWSHandler derives the ws:// upstream from the http:// service URL.
//
// Derived rather than concatenated: a hardcoded "ws://" works in compose and
// fails behind TLS in staging, which is the worst possible place to discover it.
func NewSpeakingWSHandler(speakingServiceURL string, logger zerolog.Logger) (*SpeakingWSHandler, error) {
	parsed, err := url.Parse(strings.TrimSpace(speakingServiceURL))
	if err != nil {
		return nil, fmt.Errorf("speaking service URL is not a URL: %w", err)
	}
	switch parsed.Scheme {
	case "http", "ws":
		parsed.Scheme = "ws"
	case "https", "wss":
		parsed.Scheme = "wss"
	default:
		return nil, fmt.Errorf("speaking service URL has unsupported scheme %q", parsed.Scheme)
	}
	if parsed.Host == "" {
		return nil, fmt.Errorf("speaking service URL has no host: %q", speakingServiceURL)
	}
	parsed.Path = strings.TrimSuffix(parsed.Path, "/") + "/ws"

	return &SpeakingWSHandler{
		upstreamWSURL: parsed.String(),
		dialer: &fastws.Dialer{
			// Short by design: this bounds the CONNECT, not the session. A slow
			// dial should 502 quickly rather than hold the client's upgrade open.
			HandshakeTimeout: 10 * time.Second,
		},
		logger: logger,
	}, nil
}

// Upgrade is the pre-upgrade guard. It runs as an ordinary Fiber handler with
// the full middleware chain already applied, which is what makes "authenticated
// at upgrade time, not after" true without a line of new auth code: this route
// is mounted inside the /api group, so middleware.JWT has already rejected a
// missing, expired or blacklisted token before the socket exists.
func (h *SpeakingWSHandler) Upgrade(c *fiber.Ctx) error {
	return h.upgrade(c, false)
}

// UpgradeExam is mounted only inside the paid Exam route group and after the
// session-ownership check. It marks the upstream leg as exam-only without
// trusting a client frame to select that privileged mode.
func (h *SpeakingWSHandler) UpgradeExam(c *fiber.Ctx) error {
	return h.upgrade(c, true)
}

func (h *SpeakingWSHandler) upgrade(c *fiber.Ctx, examMode bool) error {
	if !websocket.IsWebSocketUpgrade(c) {
		// 426, not 400: a plain GET here is a client bug, and 426 says which one.
		return fiber.NewError(fiber.StatusUpgradeRequired, "this endpoint requires a WebSocket upgrade")
	}

	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	correlationID, _ := c.Locals(middleware.ContextKeyRequestID).(string)

	// utils.CopyString on everything retained past this handler. Fiber recycles
	// *fiber.Ctx the moment it returns and fasthttp's header/args strings are
	// buffer-backed, so a retained slice reads as a LATER request's bytes -- here
	// that would mean logging one user's session under another user's id.
	c.Locals(localsSpeakingUserID, utils.CopyString(userID))
	c.Locals(localsSpeakingCorrelation, utils.CopyString(correlationID))
	c.Locals(localsSpeakingTraceparent, utils.CopyString(c.Query("traceparent")))
	if examMode {
		c.Locals(localsSpeakingExamMode, true)
		c.Locals(localsSpeakingExamSession, utils.CopyString(c.Query("exam_session_id")))
	}
	c.Locals(middleware.ContextKeyUpstream, "speaking")

	return c.Next()
}

// Proxy runs after a successful upgrade, wrapped by websocket.New.
func (h *SpeakingWSHandler) Proxy(clientConn *websocket.Conn) {
	defer clientConn.Close()

	userID, _ := clientConn.Locals(localsSpeakingUserID).(string)
	correlationID, _ := clientConn.Locals(localsSpeakingCorrelation).(string)
	traceparent, _ := clientConn.Locals(localsSpeakingTraceparent).(string)
	examSessionID, _ := clientConn.Locals(localsSpeakingExamSession).(string)
	examMode, _ := clientConn.Locals(localsSpeakingExamMode).(bool)

	target := h.upstreamWSURL
	if examMode {
		target += "/exam"
	}
	if traceparent != "" {
		// Speaking parses ?traceparent= at upgrade to link its Langfuse spans to
		// the caller's trace. Dropping it here would silently orphan every
		// speaking trace behind the proxy.
		target += "?traceparent=" + url.QueryEscape(traceparent)
	}

	// Server-to-server, so unlike the browser we CAN set handshake headers.
	upstreamHeaders := http.Header{}
	if correlationID != "" {
		upstreamHeaders.Set(middleware.HeaderCorrelationID, correlationID)
	}
	// GOA-030. The identity the token proved, forwarded the way every other
	// proxied route forwards it.
	//
	// This relay is byte-for-byte in both directions, which is right for audio
	// but meant the `userId` inside the client's session_init frame reached
	// Speaking unexamined -- so an authenticated caller could attribute a
	// session to any user id they typed. That is the same defect GOA-132 closed
	// on the REST side ("Sourcing userId from the validated JWT here closes
	// that, because the caller no longer controls the value"); only the socket
	// half was left open.
	//
	// Two things ride on this id and both were exploitable: sessions are
	// persisted and listed by it, and the daily speaking quota is keyed on it --
	// so a fresh id per connection bought unmetered STT and LLM spend.
	//
	// Sent as a header rather than by rewriting the frame, so the relay stays a
	// relay. Speaking prefers it over the frame's field; see
	// HandleInterviewWebSocket.
	if userID != "" {
		upstreamHeaders.Set("X-User-Id", userID)
	}
	if examMode {
		upstreamHeaders.Set("X-Exam-Session-Id", examSessionID)
	}

	started := time.Now()
	log := h.logger.With().
		Str("user_id", userID).
		Str("correlation_id", correlationID).
		Logger()

	upstreamConn, resp, err := h.dialer.Dial(target, upstreamHeaders)
	if err != nil {
		status := 0
		if resp != nil {
			status = resp.StatusCode
			resp.Body.Close()
		}
		log.Error().Err(err).Int("upstream_status", status).Msg("speaking ws: upstream dial failed")
		// 1011 (internal error) with a reason, so the browser can distinguish
		// "the backend is down" from "your connection dropped".
		_ = clientConn.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseInternalServerErr, "speaking service unavailable"),
			time.Now().Add(2*time.Second),
		)
		return
	}
	defer upstreamConn.Close()

	log.Info().Msg("speaking ws: session opened")

	var bytesUp, bytesDown int64
	var closeOnce sync.Once
	// closeBoth is what guarantees the *other* copy loop wakes up: a goroutine
	// blocked in ReadMessage only returns when its connection is closed, so
	// closing both is the shutdown signal.
	closeBoth := func() {
		closeOnce.Do(func() {
			_ = clientConn.Close()
			_ = upstreamConn.Close()
		})
	}

	var wg sync.WaitGroup
	wg.Add(2)

	// Client -> Speaking (audio frames).
	go func() {
		defer wg.Done()
		defer closeBoth()
		n, err := relay(clientConn, upstreamConn)
		bytesUp = n
		if err != nil && !isNormalClosure(err) {
			log.Debug().Err(err).Msg("speaking ws: client leg ended")
		}
	}()

	// Speaking -> client (transcript, per-criterion, evaluation, TTS audio).
	go func() {
		defer wg.Done()
		defer closeBoth()
		n, err := relay(upstreamConn, clientConn)
		bytesDown = n
		if closeErr, ok := err.(*fastws.CloseError); ok {
			// Relay the upstream's close code and reason verbatim. Collapsing
			// Speaking's 1008 + "you have used your practice time for today"
			// (GOA-034 quota) into a generic 1006 turns a policy decision into an
			// indistinguishable outage.
			_ = clientConn.WriteControl(
				websocket.CloseMessage,
				websocket.FormatCloseMessage(closeErr.Code, closeErr.Text),
				time.Now().Add(2*time.Second),
			)
		} else if err != nil && !isNormalClosure(err) {
			log.Debug().Err(err).Msg("speaking ws: upstream leg ended")
		}
	}()

	// Returning before BOTH legs exit leaks a goroutine per session, which on a
	// route this cheap to open is a denial-of-service vector rather than an
	// untidiness.
	wg.Wait()

	log.Info().
		Float64("duration_s", time.Since(started).Seconds()).
		Int64("bytes_up", bytesUp).
		Int64("bytes_down", bytesDown).
		Msg("speaking ws: session closed")
}

// relay copies frames one-for-one from src to dst until either side closes.
//
// Three properties are load-bearing and none of them are incidental:
//
//  1. The message TYPE is preserved. Audio up and TTS audio down are binary;
//     transcript, criterion and evaluation frames are text. Forcing everything
//     to text corrupts PCM (invalid UTF-8 in a text frame is a protocol
//     violation and browsers drop the connection); forcing everything to binary
//     makes the browser's `data instanceof Blob` check treat JSON as audio.
//
//  2. No buffering, batching or re-framing: one message in, one message out,
//     immediately. GOA-032 exists to get each criterion to the user the moment
//     its agent finishes; a proxy that coalesces frames deletes that benefit
//     while leaving both tickets' own tests green.
//
//  3. Deadlines are refreshed per frame, so they reap a wedged connection
//     without capping a healthy long session.
func relay(src, dst wsConn) (int64, error) {
	var total int64
	for {
		if err := src.SetReadDeadline(time.Now().Add(speakingWSDeadline)); err != nil {
			return total, err
		}
		messageType, payload, err := src.ReadMessage()
		if err != nil {
			return total, err
		}
		total += int64(len(payload))

		if err := dst.SetWriteDeadline(time.Now().Add(speakingWSDeadline)); err != nil {
			return total, err
		}
		if err := dst.WriteMessage(messageType, payload); err != nil {
			return total, err
		}
	}
}

// isNormalClosure reports whether an error is an ordinary end-of-session rather
// than a fault worth logging.
func isNormalClosure(err error) bool {
	if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
		return true
	}
	// Once closeBoth has fired, the other leg's blocked Read returns "use of
	// closed network connection". That is the shutdown working, not a failure.
	return strings.Contains(err.Error(), "use of closed network connection")
}
