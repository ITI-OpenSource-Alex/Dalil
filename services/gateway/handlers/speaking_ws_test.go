package handlers

import (
	"io"
	"net"
	"net/http"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	fastws "github.com/fasthttp/websocket"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/websocket/v2"
	"github.com/rs/zerolog"
)

func TestNewSpeakingWSHandler_DerivesUpstreamURL(t *testing.T) {
	tests := []struct {
		name    string
		in      string
		want    string
		wantErr bool
	}{
		{"http becomes ws", "http://speaking:8082", "ws://speaking:8082/ws", false},
		// The reason this is derived rather than concatenated: a hardcoded
		// "ws://" passes in compose and fails behind TLS in staging.
		{"https becomes wss", "https://speaking.example.com", "wss://speaking.example.com/ws", false},
		{"trailing slash is not doubled", "http://speaking:8082/", "ws://speaking:8082/ws", false},
		{"ws is accepted as-is", "ws://speaking:8082", "ws://speaking:8082/ws", false},
		{"unsupported scheme is rejected", "ftp://speaking:8082", "", true},
		{"missing host is rejected", "http://", "", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			h, err := NewSpeakingWSHandler(tt.in, zerolog.Nop())
			if tt.wantErr {
				if err == nil {
					t.Fatalf("expected an error for %q, got %q", tt.in, h.upstreamWSURL)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if h.upstreamWSURL != tt.want {
				t.Errorf("upstream = %q, want %q", h.upstreamWSURL, tt.want)
			}
		})
	}
}

// listenApp starts a Fiber app on an ephemeral port and returns its host:port.
// Real listeners are required because app.Test cannot carry a WebSocket upgrade.
func listenApp(t *testing.T, app *fiber.App) string {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	go func() { _ = app.Listener(ln) }()
	t.Cleanup(func() { _ = app.Shutdown() })

	// Wait for the listener to accept, so a fast test does not race startup.
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		conn, err := net.DialTimeout("tcp", ln.Addr().String(), 200*time.Millisecond)
		if err == nil {
			conn.Close()
			return ln.Addr().String()
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("app never started listening")
	return ""
}

// fakeSpeakingUpstream stands in for the Speaking service's /ws endpoint.
type fakeSpeakingUpstream struct {
	addr    string
	headers chan http.Header
}

func newFakeSpeakingUpstream(t *testing.T, handler func(*websocket.Conn)) *fakeSpeakingUpstream {
	t.Helper()
	up := &fakeSpeakingUpstream{headers: make(chan http.Header, 4)}
	app := fiber.New(fiber.Config{DisableStartupMessage: true})
	app.Get("/ws", func(c *fiber.Ctx) error {
		captured := http.Header{}
		c.Request().Header.VisitAll(func(k, v []byte) {
			captured.Set(string(k), string(v))
		})
		select {
		case up.headers <- captured:
		default:
		}
		return c.Next()
	}, websocket.New(handler))
	up.addr = listenApp(t, app)
	return up
}

// newProxyApp builds a Gateway app with the speaking WS route mounted behind a
// stub auth middleware, so the proxy can be exercised without Redis or a real
// token service.
func newProxyApp(t *testing.T, upstreamAddr string, authorized bool) string {
	t.Helper()
	h, err := NewSpeakingWSHandler("http://"+upstreamAddr, zerolog.Nop())
	if err != nil {
		t.Fatalf("handler: %v", err)
	}
	app := fiber.New(fiber.Config{DisableStartupMessage: true})
	app.Use(func(c *fiber.Ctx) error {
		if !authorized {
			// Exactly what middleware.JWT does on a missing/expired token.
			return fiber.NewError(fiber.StatusUnauthorized, "missing or invalid authorization token")
		}
		c.Locals(middleware.ContextKeyUserID, "user-1")
		c.Locals(middleware.ContextKeyRequestID, "corr-test-1")
		return c.Next()
	})
	app.Get("/api/speaking/ws", h.Upgrade, websocket.New(h.Proxy))
	return listenApp(t, app)
}

func dialProxy(t *testing.T, addr string) (*fastws.Conn, *http.Response, error) {
	t.Helper()
	conn, resp, err := (&fastws.Dialer{HandshakeTimeout: 5 * time.Second}).
		Dial("ws://"+addr+"/api/speaking/ws", nil)
	if conn != nil {
		t.Cleanup(func() { conn.Close() })
	}
	return conn, resp, err
}

// TestSpeakingWS_RejectedBeforeSocketOpens is the acceptance criterion: an
// unauthenticated upgrade is refused BEFORE the socket exists, not by opening
// one and closing it afterwards. The assertion is on the HTTP status, because
// that is the only thing that distinguishes the two.
func TestSpeakingWS_RejectedBeforeSocketOpens(t *testing.T) {
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {
		t.Error("upstream was dialled for an unauthenticated request")
	})
	addr := newProxyApp(t, upstream.addr, false)

	conn, resp, err := dialProxy(t, addr)
	if err == nil {
		conn.Close()
		t.Fatal("expected the upgrade to be refused")
	}
	if resp == nil {
		t.Fatalf("expected an HTTP response carrying the rejection, got transport error: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != fiber.StatusUnauthorized {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, want 401 (body: %s)", resp.StatusCode, body)
	}
}

// TestSpeakingWS_NonUpgradeRequestReturns426 -- a plain GET here is a client
// bug, and 426 names it. 400 would not.
func TestSpeakingWS_NonUpgradeRequestReturns426(t *testing.T) {
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {})
	addr := newProxyApp(t, upstream.addr, true)

	resp, err := http.Get("http://" + addr + "/api/speaking/ws")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != fiber.StatusUpgradeRequired {
		t.Fatalf("status = %d, want 426", resp.StatusCode)
	}
}

// TestSpeakingWS_FramesRelayedUnbuffered is the test that proves GOA-032
// survives GOA-132: neither ticket's own suite would catch a proxy that
// coalesces frames, because each half works perfectly in isolation.
//
// The upstream blocks after its first frame until the test confirms the client
// received it. A buffering proxy deadlocks here rather than merely being slow.
func TestSpeakingWS_FramesRelayedUnbuffered(t *testing.T) {
	clientGotFirst := make(chan struct{})
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {
		if err := c.WriteMessage(websocket.TextMessage, []byte(`{"type":"criterion","criterion":"Fluency and Coherence"}`)); err != nil {
			return
		}
		select {
		case <-clientGotFirst:
		case <-time.After(5 * time.Second):
			return
		}
		_ = c.WriteMessage(websocket.TextMessage, []byte(`{"type":"criterion","criterion":"Lexical Resource"}`))
		_ = c.WriteMessage(websocket.TextMessage, []byte(`{"type":"evaluation","overall_band":7}`))
		// Binary last, so the opcode assertion below cannot pass by accident.
		_ = c.WriteMessage(websocket.BinaryMessage, []byte{0xDE, 0xAD, 0xBE, 0xEF})
	})
	addr := newProxyApp(t, upstream.addr, true)

	conn, _, err := dialProxy(t, addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))

	msgType, payload, err := conn.ReadMessage()
	if err != nil {
		t.Fatalf("first frame: %v", err)
	}
	if msgType != websocket.TextMessage {
		t.Fatalf("first frame type = %d, want text", msgType)
	}
	if !strings.Contains(string(payload), "Fluency and Coherence") {
		t.Fatalf("first frame = %s", payload)
	}
	close(clientGotFirst)

	for i, want := range []struct {
		msgType int
		body    string
	}{
		{websocket.TextMessage, "Lexical Resource"},
		{websocket.TextMessage, "evaluation"},
		{websocket.BinaryMessage, ""},
	} {
		msgType, payload, err := conn.ReadMessage()
		if err != nil {
			t.Fatalf("frame %d: %v", i+2, err)
		}
		if msgType != want.msgType {
			t.Errorf("frame %d type = %d, want %d -- the proxy must preserve the opcode; "+
				"text-as-binary makes the browser treat JSON as audio and binary-as-text corrupts PCM",
				i+2, msgType, want.msgType)
		}
		if want.body != "" && !strings.Contains(string(payload), want.body) {
			t.Errorf("frame %d = %s, want it to contain %q", i+2, payload, want.body)
		}
		if want.msgType == websocket.BinaryMessage {
			if len(payload) != 4 || payload[0] != 0xDE || payload[3] != 0xEF {
				t.Errorf("binary payload corrupted in transit: %v", payload)
			}
		}
	}
}

// TestSpeakingWS_ClientFramesReachUpstream covers the other direction: the
// browser's audio must arrive upstream as binary, unaltered.
func TestSpeakingWS_ClientFramesReachUpstream(t *testing.T) {
	received := make(chan struct {
		msgType int
		payload []byte
	}, 4)
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {
		for i := 0; i < 2; i++ {
			msgType, payload, err := c.ReadMessage()
			if err != nil {
				return
			}
			cp := make([]byte, len(payload))
			copy(cp, payload)
			received <- struct {
				msgType int
				payload []byte
			}{msgType, cp}
		}
	})
	addr := newProxyApp(t, upstream.addr, true)

	conn, _, err := dialProxy(t, addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	if err := conn.WriteMessage(websocket.TextMessage, []byte(`{"type":"session_init"}`)); err != nil {
		t.Fatalf("write init: %v", err)
	}
	audio := []byte{0x00, 0x7F, 0x80, 0xFF}
	if err := conn.WriteMessage(websocket.BinaryMessage, audio); err != nil {
		t.Fatalf("write audio: %v", err)
	}

	for i, want := range []int{websocket.TextMessage, websocket.BinaryMessage} {
		select {
		case got := <-received:
			if got.msgType != want {
				t.Errorf("upstream frame %d type = %d, want %d", i, got.msgType, want)
			}
			if want == websocket.BinaryMessage && string(got.payload) != string(audio) {
				t.Errorf("audio corrupted upstream: %v", got.payload)
			}
		case <-time.After(5 * time.Second):
			t.Fatalf("upstream never received frame %d", i)
		}
	}
}

// TestSpeakingWS_CorrelationIDForwarded is GOA-132's integration criterion.
// Without it, Speaking's logs for a proxied session cannot be joined to the
// Gateway request that opened them.
func TestSpeakingWS_CorrelationIDForwarded(t *testing.T) {
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {
		_, _, _ = c.ReadMessage()
	})
	addr := newProxyApp(t, upstream.addr, true)

	conn, _, err := dialProxy(t, addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	_ = conn.WriteMessage(websocket.TextMessage, []byte("hello"))

	select {
	case headers := <-upstream.headers:
		if got := headers.Get(middleware.HeaderCorrelationID); got != "corr-test-1" {
			t.Errorf("upstream %s = %q, want %q", middleware.HeaderCorrelationID, got, "corr-test-1")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("upstream handshake headers were never captured")
	}
}

// TestSpeakingWS_UpstreamCloseCodeRelayed keeps a policy decision from reading
// as an outage. Speaking closes with 1008 and a reason when a user exhausts
// their daily practice budget (GOA-034); collapsing that to a generic 1006
// leaves the UI unable to explain what happened.
func TestSpeakingWS_UpstreamCloseCodeRelayed(t *testing.T) {
	const reason = "You have used your speaking practice time for today."
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {
		_ = c.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.ClosePolicyViolation, reason),
			time.Now().Add(2*time.Second),
		)
		_ = c.Close()
	})
	addr := newProxyApp(t, upstream.addr, true)

	conn, _, err := dialProxy(t, addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))

	_, _, readErr := conn.ReadMessage()
	closeErr, ok := readErr.(*fastws.CloseError)
	if !ok {
		t.Fatalf("expected a close error, got %T: %v", readErr, readErr)
	}
	if closeErr.Code != websocket.ClosePolicyViolation {
		t.Errorf("close code = %d, want %d", closeErr.Code, websocket.ClosePolicyViolation)
	}
	if closeErr.Text != reason {
		t.Errorf("close reason = %q, want %q", closeErr.Text, reason)
	}
}

// TestSpeakingWS_UpstreamUnavailableClosesCleanly -- a dead backend must not
// leave the browser holding an open socket that never speaks.
func TestSpeakingWS_UpstreamUnavailableClosesCleanly(t *testing.T) {
	// Port 1 is reserved and never listening.
	addr := newProxyApp(t, "127.0.0.1:1", true)

	conn, _, err := dialProxy(t, addr)
	if err != nil {
		t.Fatalf("the client upgrade itself should succeed: %v", err)
	}
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))

	_, _, readErr := conn.ReadMessage()
	if readErr == nil {
		t.Fatal("expected the socket to be closed when the upstream is unreachable")
	}
	if closeErr, ok := readErr.(*fastws.CloseError); ok {
		if closeErr.Code != websocket.CloseInternalServerErr {
			t.Errorf("close code = %d, want %d", closeErr.Code, websocket.CloseInternalServerErr)
		}
	}
}

// TestSpeakingWS_NoGoroutineLeak. Both relay legs must exit before Proxy
// returns; on a route this cheap to open, one leaked goroutine per session is a
// denial-of-service vector rather than untidiness.
func TestSpeakingWS_NoGoroutineLeak(t *testing.T) {
	upstream := newFakeSpeakingUpstream(t, func(c *websocket.Conn) {
		_, _, _ = c.ReadMessage()
	})
	addr := newProxyApp(t, upstream.addr, true)

	// Warm up so one-off server goroutines are not counted as the leak.
	for i := 0; i < 3; i++ {
		conn, _, err := dialProxy(t, addr)
		if err != nil {
			t.Fatalf("warmup dial: %v", err)
		}
		conn.Close()
	}
	time.Sleep(300 * time.Millisecond)
	baseline := runtime.NumGoroutine()

	const sessions = 25
	for i := 0; i < sessions; i++ {
		conn, _, err := dialProxy(t, addr)
		if err != nil {
			t.Fatalf("dial %d: %v", i, err)
		}
		_ = conn.WriteMessage(websocket.TextMessage, []byte("x"))
		conn.Close()
	}

	settled := false
	for i := 0; i < 20; i++ {
		time.Sleep(100 * time.Millisecond)
		if runtime.NumGoroutine() <= baseline+5 {
			settled = true
			break
		}
	}
	if !settled {
		t.Errorf("goroutines leaked across %d sessions: baseline %d, now %d",
			sessions, baseline, runtime.NumGoroutine())
	}
}
