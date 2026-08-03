package handlers

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// Reproduces the intermittent SSE truncation seen in production: a chat stream
// that emits its metadata frame immediately, then goes quiet while RAG
// generates, and is severed before the tokens arrive. The client sees
// "peer closed connection without sending complete message body" and the
// Gateway logs a 200, which is close to undiagnosable from the outside.
//
// The gap is the whole point. Orchestration sends `metadata` within
// milliseconds and the first token only after RAG returns -- measured at a
// median of 14s and a p90 of 33s -- so the connection is open and idle for
// tens of seconds mid-response. Any deadline that applies to the whole response
// rather than to each write will fire in that window.
//
// Deliberately no LLM and no network: a fake upstream reproduces the timing for
// free, which a 1-in-13 production flake could never do reliably.
func TestSlowUpstreamStreamIsNotTruncatedMidResponse(t *testing.T) {
	const gap = 3 * time.Second

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		flusher, ok := w.(http.Flusher)
		if !ok {
			t.Error("upstream ResponseWriter cannot flush")
			return
		}

		// The metadata frame, immediately -- exactly what Orchestration does.
		fmt.Fprint(w, "event: metadata\ndata: {\"type\":\"metadata\"}\n\n")
		flusher.Flush()

		// The silence while the model works.
		time.Sleep(gap)

		fmt.Fprint(w, "event: token\ndata: {\"type\":\"token\",\"content\":\"done\"}\n\n")
		flusher.Flush()
	}))
	defer upstream.Close()

	// A Gateway configured the way the real one is: a write timeout far shorter
	// than the gap above.
	app := fiber.New(fiber.Config{
		ReadTimeout:  1 * time.Second,
		WriteTimeout: 1 * time.Second,
	})
	handler := NewStreamHandler(upstream.Client(), upstream.URL, "", "internal-key")
	app.Post("/api/chat", func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "user-123")
		return handler.Chat(c)
	})

	// A real TCP listener, not app.Test(). app.Test() drives the handler over an
	// in-memory transport where no socket deadline exists, so it cannot show this
	// defect at all -- the first version of this test passed against a Gateway
	// that truncates every slow stream in production.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	go func() { _ = app.Listener(listener) }()
	defer app.Shutdown()
	time.Sleep(150 * time.Millisecond)

	client := &http.Client{Timeout: gap + 10*time.Second}
	resp, err := client.Post(
		"http://"+listener.Addr().String()+"/api/chat",
		"application/json",
		strings.NewReader(`{"message":"hi"}`),
	)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	raw, readErr := io.ReadAll(resp.Body)
	received := string(raw)

	if !strings.Contains(received, "metadata") {
		t.Fatalf("the metadata frame never arrived: %q", received)
	}
	// The assertion that matters. A truncated stream carries the metadata frame
	// and stops, with a 200 status and no error anywhere.
	if readErr != nil {
		t.Fatalf("stream was severed mid-response: %v (received %q)", readErr, received)
	}
	if !strings.Contains(received, "done") {
		t.Fatalf(
			"stream was severed after the metadata frame -- the token that arrived %s later was lost. Received: %q",
			gap, received,
		)
	}
}
