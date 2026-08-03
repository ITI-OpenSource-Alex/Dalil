package handlers

import (
	"bufio"
	"crypto/tls"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
)

// handshakeRequestHeaders are the client headers the upgrade must carry upstream.
//
// Sec-WebSocket-Key is the load-bearing one: the Sec-WebSocket-Accept the
// upstream computes is derived from it, and the browser verifies that value
// against the key it sent. Minting a fresh key here would make every handshake
// fail client-side even though both hops individually looked healthy.
var handshakeRequestHeaders = []string{
	fiber.HeaderConnection,
	fiber.HeaderUpgrade,
	"Sec-WebSocket-Key",
	"Sec-WebSocket-Version",
	"Sec-WebSocket-Protocol",
	"Sec-WebSocket-Extensions",
	fiber.HeaderOrigin,
}

// handshakeResponseHeaders are the upstream 101 headers the client must receive.
var handshakeResponseHeaders = []string{
	fiber.HeaderUpgrade,
	fiber.HeaderConnection,
	"Sec-WebSocket-Accept",
	"Sec-WebSocket-Protocol",
	"Sec-WebSocket-Extensions",
}

// SpeakingWSHandler proxies the Speaking exam WebSocket upgrade.
//
// The frontend used to open this socket straight against the Speaking service on
// :8082, which meant the connection carried no JWT, no tier check and no exam
// session ownership -- the same class of exposure the HTTP routes closed in
// BUG-046. Routing the upgrade through the Gateway puts it behind the same
// middleware chain as everything else.
type SpeakingWSHandler struct {
	speakingServiceURL string
	dialTimeout        time.Duration
	logger             zerolog.Logger
}

func NewSpeakingWSHandler(
	speakingServiceURL string,
	dialTimeout time.Duration,
	logger zerolog.Logger,
) *SpeakingWSHandler {
	if dialTimeout <= 0 {
		dialTimeout = 10 * time.Second
	}
	return &SpeakingWSHandler{
		speakingServiceURL: strings.TrimRight(speakingServiceURL, "/"),
		dialTimeout:        dialTimeout,
		logger:             logger,
	}
}

// Proxy tunnels the upgrade rather than terminating it.
//
// The Gateway completes the handshake with the upstream first, mirrors the
// resulting 101 back to the client, then hands both sockets to a byte pump. It
// deliberately does not decode WebSocket frames: Speaking exchanges binary audio
// and JSON control frames whose shapes are none of the Gateway's business, and a
// transparent tunnel cannot corrupt a payload it never parses. It also keeps the
// Gateway free of a WebSocket library -- fasthttp connection hijacking is enough.
func (h *SpeakingWSHandler) Proxy(c *fiber.Ctx) error {
	if !isWebSocketUpgrade(c) {
		return fiber.NewError(fiber.StatusBadRequest, "expected a websocket upgrade request")
	}

	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	examSessionID := c.Query("exam_session_id")
	if examSessionID == "" {
		return fiber.NewError(fiber.StatusBadRequest, "exam_session_id is required")
	}

	target, err := speakingUpstreamURL(h.speakingServiceURL, examSessionID, userID)
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "speaking service URL is invalid")
	}

	c.Locals(middleware.ContextKeyUpstream, "speaking")

	upstream, err := dialUpstream(target, h.dialTimeout)
	if err != nil {
		h.logger.Error().
			Err(err).
			Str("exam_session_id", examSessionID).
			Msg("speaking websocket dial failed")
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact speaking service")
	}

	req, err := h.upgradeRequest(c, target)
	if err != nil {
		upstream.Close()
		return err
	}
	if err := req.Write(upstream); err != nil {
		upstream.Close()
		h.logger.Error().
			Err(err).
			Str("exam_session_id", examSessionID).
			Msg("speaking websocket handshake write failed")
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact speaking service")
	}

	// The reader is retained past the handshake: http.ReadResponse may have
	// buffered the first frames along with the 101 headers, and dropping it would
	// silently swallow them.
	upstreamReader := bufio.NewReader(upstream)
	resp, err := http.ReadResponse(upstreamReader, req)
	if err != nil {
		upstream.Close()
		h.logger.Error().
			Err(err).
			Str("exam_session_id", examSessionID).
			Msg("speaking websocket handshake read failed")
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact speaking service")
	}

	if resp.StatusCode != http.StatusSwitchingProtocols {
		defer upstream.Close()
		return relayFailedUpgrade(c, resp)
	}

	c.Status(fiber.StatusSwitchingProtocols)
	// fasthttp omits Content-Length and Content-Type for 1xx, but the default
	// content type is set on the context before the status is, so clear it
	// explicitly rather than relying on that ordering.
	c.Response().Header.Del(fiber.HeaderContentType)
	for _, name := range handshakeResponseHeaders {
		if value := resp.Header.Get(name); value != "" {
			c.Set(name, value)
		}
	}

	// fasthttp writes the 101 above, then invokes this handler with the raw client
	// connection and closes it on return.
	c.Context().Hijack(func(client net.Conn) {
		defer upstream.Close()
		tunnel(client, upstream, upstreamReader)
	})
	return nil
}

// tunnel copies in both directions until either side stops.
//
// It returns as soon as one direction ends so the caller can close the upstream,
// which unblocks the other copy. Waiting for both instead would leak a goroutine
// per abandoned connection for as long as the surviving half stayed open.
func tunnel(client net.Conn, upstream net.Conn, upstreamReader io.Reader) {
	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(upstream, client)
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(client, upstreamReader)
		done <- struct{}{}
	}()
	<-done
}

func (h *SpeakingWSHandler) upgradeRequest(c *fiber.Ctx, target *url.URL) (*http.Request, error) {
	req, err := http.NewRequest(http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, fiber.NewError(fiber.StatusInternalServerError, "failed to build upgrade request")
	}
	for _, name := range handshakeRequestHeaders {
		if value := c.Get(name); value != "" {
			req.Header.Set(name, value)
		}
	}
	if correlationID, _ := c.Locals(middleware.ContextKeyRequestID).(string); correlationID != "" {
		req.Header.Set(middleware.HeaderCorrelationID, correlationID)
	}
	if chain := middleware.ForwardedForChain(c); chain != "" {
		req.Header.Set(middleware.HeaderForwardedFor, chain)
	}
	return req, nil
}

// relayFailedUpgrade passes an upstream rejection through instead of flattening
// it into a generic 502, so a "Too Many Requests" from the Speaking service's
// connection cap still reads as 429 at the edge.
func relayFailedUpgrade(c *fiber.Ctx, resp *http.Response) error {
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	c.Status(resp.StatusCode)
	if contentType := resp.Header.Get(fiber.HeaderContentType); contentType != "" {
		c.Set(fiber.HeaderContentType, contentType)
	}
	return c.Send(body)
}

func isWebSocketUpgrade(c *fiber.Ctx) bool {
	if !strings.EqualFold(c.Get(fiber.HeaderUpgrade), "websocket") {
		return false
	}
	// Connection is a comma-separated list and may carry other tokens.
	for _, token := range strings.Split(c.Get(fiber.HeaderConnection), ",") {
		if strings.EqualFold(strings.TrimSpace(token), "upgrade") {
			return true
		}
	}
	return false
}

// speakingUpstreamURL builds the upstream /ws URL.
//
// exam_session_id is forwarded so the Speaking service can associate the socket
// with the exam session, and user_id comes from the validated JWT rather than the
// client's query string -- the socket otherwise self-reports its identity in its
// first text frame, which a candidate could set to anyone.
func speakingUpstreamURL(baseURL string, examSessionID string, userID string) (*url.URL, error) {
	target, err := url.Parse(baseURL)
	if err != nil {
		return nil, err
	}
	// A ws:// base is accepted for convenience; the handshake itself is HTTP.
	switch target.Scheme {
	case "ws":
		target.Scheme = "http"
	case "wss":
		target.Scheme = "https"
	case "http", "https":
	default:
		return nil, &url.Error{Op: "parse", URL: baseURL, Err: net.UnknownNetworkError(target.Scheme)}
	}
	if target.Host == "" {
		return nil, &url.Error{Op: "parse", URL: baseURL, Err: net.UnknownNetworkError("missing host")}
	}

	target.Path = strings.TrimSuffix(target.Path, "/") + "/ws"
	query := target.Query()
	query.Set("exam_session_id", examSessionID)
	query.Set("user_id", userID)
	target.RawQuery = query.Encode()
	return target, nil
}

func dialUpstream(target *url.URL, timeout time.Duration) (net.Conn, error) {
	address := target.Host
	if target.Port() == "" {
		if target.Scheme == "https" {
			address = net.JoinHostPort(address, "443")
		} else {
			address = net.JoinHostPort(address, "80")
		}
	}

	if target.Scheme == "https" {
		return tls.DialWithDialer(
			&net.Dialer{Timeout: timeout},
			"tcp",
			address,
			&tls.Config{ServerName: target.Hostname()},
		)
	}
	return net.DialTimeout("tcp", address, timeout)
}
