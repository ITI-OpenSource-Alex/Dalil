package handlers

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// GOA-038. The user id Orchestration erases by must come from the validated
// JWT, never from anything the caller can write. Without that, DELETE
// /api/sessions/memory is a destructive operation any authenticated user can
// aim at any other user by naming them.
func TestChatMemoryForwardsTheAuthenticatedUserNotTheRequestBody(t *testing.T) {
	var seenUser, seenKey, seenMethod string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/sessions/memory" {
			t.Fatalf("unexpected upstream path %q", r.URL.Path)
		}
		seenMethod = r.Method
		seenUser = r.Header.Get("X-User-Id")
		seenKey = r.Header.Get("X-Internal-API-Key")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"factsDeleted":3,"sessionsCleared":2}`))
	}))
	defer upstream.Close()

	handler := NewStreamHandler(upstream.Client(), upstream.URL, "", "internal-key")
	app := fiber.New()
	app.Delete("/api/sessions/memory", func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "user-from-jwt")
		return handler.ChatMemory(c)
	})

	// The body names someone else. It must have no effect whatsoever.
	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/sessions/memory?userId=victim",
		nil,
	)
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
	if seenMethod != http.MethodDelete {
		t.Fatalf("expected DELETE upstream, got %q", seenMethod)
	}
	if seenUser != "user-from-jwt" {
		t.Fatalf("expected the JWT subject to be forwarded, got %q", seenUser)
	}
	if seenKey != "internal-key" {
		t.Fatalf("expected the internal API key to be forwarded, got %q", seenKey)
	}
}

// An unauthenticated request must never reach Orchestration at all. The route
// sits inside the /api JWT group in production; this asserts the handler itself
// does not proceed if that middleware is ever removed or reordered.
func TestChatMemoryRefusesWithoutAnAuthenticatedUser(t *testing.T) {
	called := false
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	handler := NewStreamHandler(upstream.Client(), upstream.URL, "", "internal-key")
	app := fiber.New()
	app.Delete("/api/sessions/memory", handler.ChatMemory)

	response, err := app.Test(httptest.NewRequest(http.MethodDelete, "/api/sessions/memory", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()

	if called {
		t.Fatal("orchestration was called for an unauthenticated erasure request")
	}
	if response.StatusCode == http.StatusOK {
		t.Fatal("expected an error status for an unauthenticated request")
	}
}

// The response is JSON and small. Relaying it through the SSE stream helper
// would set Accept: text/event-stream and stream a body that does not exist.
func TestChatMemoryRelaysTheUpstreamStatusAndBody(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"detail":"Memory store unavailable"}`))
	}))
	defer upstream.Close()

	handler := NewStreamHandler(upstream.Client(), upstream.URL, "", "internal-key")
	app := fiber.New()
	app.Delete("/api/sessions/memory", func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "user-from-jwt")
		return handler.ChatMemory(c)
	})

	response, err := app.Test(httptest.NewRequest(http.MethodDelete, "/api/sessions/memory", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("a failed erasure must not be reported as success: got %d", response.StatusCode)
	}
}
