package handlers

import (
	"bufio"
	"crypto/sha1"
	"encoding/base64"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
)

const (
	wsTestUserID    = "44444444-4444-4444-4444-444444444444"
	wsTestSessionID = "55555555-5555-5555-5555-555555555555"
	// Fixed 16-byte base64 key so the expected Sec-WebSocket-Accept is stable.
	wsTestKey = "dGhlIHNhbXBsZSBub25jZQ=="
	// RFC 6455 GUID used to derive Sec-WebSocket-Accept from Sec-WebSocket-Key.
	wsGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
)

func TestSpeakingUpstreamURLForwardsExamSessionAndAuthoritativeUserID(t *testing.T) {
	target, err := speakingUpstreamURL("http://speaking:8082", wsTestSessionID, wsTestUserID)
	if err != nil {
		t.Fatalf("build upstream URL: %v", err)
	}

	if target.Scheme != "http" || target.Host != "speaking:8082" || target.Path != "/ws" {
		t.Fatalf("unexpected upstream URL %q", target.String())
	}
	query := target.Query()
	if query.Get("exam_session_id") != wsTestSessionID {
		t.Fatalf("expected exam_session_id to be forwarded, got %q", query.Get("exam_session_id"))
	}
	if query.Get("user_id") != wsTestUserID {
		t.Fatalf("expected user_id from the token, got %q", query.Get("user_id"))
	}
}

func TestSpeakingUpstreamURLNormalisesWebSocketSchemes(t *testing.T) {
	target, err := speakingUpstreamURL("ws://speaking:8082", wsTestSessionID, wsTestUserID)
	if err != nil {
		t.Fatalf("build upstream URL: %v", err)
	}
	if target.Scheme != "http" {
		t.Fatalf("expected ws:// to be dialled as http, got %q", target.Scheme)
	}

	secure, err := speakingUpstreamURL("wss://speaking.example", wsTestSessionID, wsTestUserID)
	if err != nil {
		t.Fatalf("build secure upstream URL: %v", err)
	}
	if secure.Scheme != "https" {
		t.Fatalf("expected wss:// to be dialled as https, got %q", secure.Scheme)
	}
}

func TestSpeakingUpstreamURLRejectsAnUnusableBase(t *testing.T) {
	if _, err := speakingUpstreamURL("speaking:8082", wsTestSessionID, wsTestUserID); err == nil {
		t.Fatal("expected a base URL without a scheme to be rejected")
	}
}

func TestNonUpgradeRequestIsRejected(t *testing.T) {
	app := newSpeakingWSTestApp(t, "http://127.0.0.1:9")

	req := httptest.NewRequest(fiber.MethodGet, "/api/exam/speaking/ws?exam_session_id="+wsTestSessionID, nil)
	resp, err := app.Test(req, -1)
	if err != nil {
		t.Fatalf("perform request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != fiber.StatusBadRequest {
		t.Fatalf("expected 400 for a plain GET, got %d", resp.StatusCode)
	}
}

func TestUpgradeWithoutExamSessionIDIsRejected(t *testing.T) {
	app := newSpeakingWSTestApp(t, "http://127.0.0.1:9")

	req := httptest.NewRequest(fiber.MethodGet, "/api/exam/speaking/ws", nil)
	setWebSocketHandshakeHeaders(req.Header)
	resp, err := app.Test(req, -1)
	if err != nil {
		t.Fatalf("perform request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != fiber.StatusBadRequest {
		t.Fatalf("expected 400 without exam_session_id, got %d", resp.StatusCode)
	}
}

func TestUnreachableSpeakingServiceReturnsBadGateway(t *testing.T) {
	// Reserved TEST-NET-1 address; nothing listens and the dial fails fast.
	app := newSpeakingWSTestApp(t, "http://192.0.2.1:9")

	req := httptest.NewRequest(fiber.MethodGet, "/api/exam/speaking/ws?exam_session_id="+wsTestSessionID, nil)
	setWebSocketHandshakeHeaders(req.Header)
	resp, err := app.Test(req, -1)
	if err != nil {
		t.Fatalf("perform request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != fiber.StatusBadGateway {
		t.Fatalf("expected 502 when speaking is unreachable, got %d", resp.StatusCode)
	}
}

// An upstream rejection must reach the client as itself. The Speaking service
// answers 429 when its connection cap is hit, and collapsing that into a 502
// would tell the UI the wrong thing to do about it.
func TestUpstreamRejectionIsRelayedVerbatim(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
	}))
	t.Cleanup(upstream.Close)

	app := newSpeakingWSTestApp(t, upstream.URL)
	req := httptest.NewRequest(fiber.MethodGet, "/api/exam/speaking/ws?exam_session_id="+wsTestSessionID, nil)
	setWebSocketHandshakeHeaders(req.Header)
	resp, err := app.Test(req, -1)
	if err != nil {
		t.Fatalf("perform request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != fiber.StatusTooManyRequests {
		t.Fatalf("expected the upstream 429 to be relayed, got %d", resp.StatusCode)
	}
}

// TestWebSocketTunnelCompletesHandshakeAndPassesBytesBothWays exercises the real
// thing: a live listener, a real handshake and raw frames in both directions.
//
// app.Test cannot cover this -- it never yields a hijackable connection -- and the
// tunnel is the one part of this ticket that no amount of unit testing can
// vouch for, since it depends on fasthttp writing a 101 and then handing over the
// socket intact.
func TestWebSocketTunnelCompletesHandshakeAndPassesBytesBothWays(t *testing.T) {
	upstreamAddr, upstreamQuery := startEchoUpgradeServer(t)
	app := newSpeakingWSTestApp(t, "http://"+upstreamAddr)

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	go func() { _ = app.Listener(listener) }()
	t.Cleanup(func() { _ = app.Shutdown() })

	client, err := net.DialTimeout("tcp", listener.Addr().String(), 5*time.Second)
	if err != nil {
		t.Fatalf("dial gateway: %v", err)
	}
	defer client.Close()
	if err := client.SetDeadline(time.Now().Add(10 * time.Second)); err != nil {
		t.Fatalf("set deadline: %v", err)
	}

	handshake := "GET /api/exam/speaking/ws?exam_session_id=" + wsTestSessionID + " HTTP/1.1\r\n" +
		"Host: " + listener.Addr().String() + "\r\n" +
		"Upgrade: websocket\r\n" +
		"Connection: Upgrade\r\n" +
		"Sec-WebSocket-Key: " + wsTestKey + "\r\n" +
		"Sec-WebSocket-Version: 13\r\n\r\n"
	if _, err := client.Write([]byte(handshake)); err != nil {
		t.Fatalf("write handshake: %v", err)
	}

	reader := bufio.NewReader(client)
	resp, err := http.ReadResponse(reader, nil)
	if err != nil {
		t.Fatalf("read handshake response: %v", err)
	}
	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("expected 101 from the gateway, got %d", resp.StatusCode)
	}
	if got := resp.Header.Get("Sec-WebSocket-Accept"); got != expectedAccept(wsTestKey) {
		t.Fatalf("expected the upstream accept token %q, got %q", expectedAccept(wsTestKey), got)
	}
	if !strings.EqualFold(resp.Header.Get("Upgrade"), "websocket") {
		t.Fatalf("expected Upgrade: websocket, got %q", resp.Header.Get("Upgrade"))
	}

	// The upstream received the handshake with the exam session id and the
	// token-derived user id, not whatever the client claimed.
	query := <-upstreamQuery
	if query.Get("exam_session_id") != wsTestSessionID {
		t.Fatalf("expected exam_session_id upstream, got %q", query.Get("exam_session_id"))
	}
	if query.Get("user_id") != wsTestUserID {
		t.Fatalf("expected user_id upstream, got %q", query.Get("user_id"))
	}

	// Client -> upstream -> client, on the hijacked socket.
	if _, err := client.Write([]byte("ping frame")); err != nil {
		t.Fatalf("write through tunnel: %v", err)
	}
	echoed := make([]byte, len("echo:ping frame"))
	if _, err := io.ReadFull(reader, echoed); err != nil {
		t.Fatalf("read through tunnel: %v", err)
	}
	if string(echoed) != "echo:ping frame" {
		t.Fatalf("expected the upstream echo, got %q", echoed)
	}
}

func newSpeakingWSTestApp(t *testing.T, speakingURL string) *fiber.App {
	t.Helper()
	handler := NewSpeakingWSHandler(speakingURL, 2*time.Second, zerolog.Nop())

	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, wsTestUserID)
		c.Locals(middleware.ContextKeyRequestID, "corr-1")
		return c.Next()
	})
	app.Get("/api/exam/speaking/ws", handler.Proxy)
	return app
}

func setWebSocketHandshakeHeaders(header http.Header) {
	header.Set("Upgrade", "websocket")
	header.Set("Connection", "Upgrade")
	header.Set("Sec-WebSocket-Key", wsTestKey)
	header.Set("Sec-WebSocket-Version", "13")
}

// startEchoUpgradeServer is a minimal WebSocket-shaped upstream: it completes the
// RFC 6455 handshake by hand and then echoes whatever bytes arrive, prefixed.
// Hand-rolling it keeps a WebSocket library out of the Gateway's dependencies,
// which is the point of the hijack-based proxy in the first place.
func startEchoUpgradeServer(t *testing.T) (string, <-chan url.Values) {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen upstream: %v", err)
	}
	t.Cleanup(func() { _ = listener.Close() })

	queries := make(chan url.Values, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()

		reader := bufio.NewReader(conn)
		req, err := http.ReadRequest(reader)
		if err != nil {
			return
		}
		queries <- req.URL.Query()

		if !strings.EqualFold(req.Header.Get("Upgrade"), "websocket") {
			_, _ = conn.Write([]byte("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"))
			return
		}
		accept := expectedAccept(req.Header.Get("Sec-WebSocket-Key"))
		_, _ = fmt.Fprintf(conn,
			"HTTP/1.1 101 Switching Protocols\r\n"+
				"Upgrade: websocket\r\n"+
				"Connection: Upgrade\r\n"+
				"Sec-WebSocket-Accept: %s\r\n\r\n", accept)

		buffer := make([]byte, 512)
		for {
			read, err := reader.Read(buffer)
			if read > 0 {
				if _, werr := conn.Write([]byte("echo:" + string(buffer[:read]))); werr != nil {
					return
				}
			}
			if err != nil {
				return
			}
		}
	}()

	return listener.Addr().String(), queries
}

func expectedAccept(key string) string {
	digest := sha1.Sum([]byte(key + wsGUID))
	return base64.StdEncoding.EncodeToString(digest[:])
}
