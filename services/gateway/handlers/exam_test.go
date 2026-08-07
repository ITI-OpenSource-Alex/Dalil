package handlers

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func TestStartListeningUsesAuthenticatedUserAndInternalKey(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/exam/listening/start" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.URL.Query().Get("user_id"); got != "user-123" {
			t.Fatalf("expected authenticated user ID, got %q", got)
		}
		if got := r.URL.Query().Get("exam_type"); got != "academic" {
			t.Fatalf("expected academic exam type, got %q", got)
		}
		if got := r.Header.Get("X-Internal-API-Key"); got != "test-key" {
			t.Fatalf("expected internal API key, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"audio_urls":["one","two","three","four"]}`))
	}))
	defer upstream.Close()

	handler := NewExamHandler(upstream.Client(), upstream.URL, "test-key")
	app := listeningTestApp(handler, "user-123")
	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/start", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestSubmitListeningDifferentSessionOwnerReturns403(t *testing.T) {
	const ownerID = "owner-123"
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/exam/listening/session-456/submit" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if r.URL.Query().Get("user_id") != ownerID {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			_, _ = w.Write([]byte(`{"detail":"Session belongs to another user"}`))
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	handler := NewExamHandler(upstream.Client(), upstream.URL, "test-key")
	app := listeningTestApp(handler, "different-user")
	request := httptest.NewRequest(
		http.MethodPut,
		"/session-456/submit",
		strings.NewReader(`{"answers":{"1":"A"}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", response.StatusCode)
	}
}

func listeningTestApp(handler *ExamHandler, userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, userID)
		return c.Next()
	})
	app.Get("/start", handler.StartListening)
	app.Put("/:sessionId/submit", handler.SubmitListening)
	return app
}

func TestGetHistoryUsesAuthenticatedUserAndForwardsPage(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/users/user-123/exam-history" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.URL.Query().Get("page"); got != "2" {
			t.Fatalf("expected page=2 forwarded, got %q", got)
		}
		if got := r.Header.Get("X-Internal-API-Key"); got != "test-key" {
			t.Fatalf("expected internal API key, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[]`))
	}))
	defer upstream.Close()

	handler := NewExamHandler(upstream.Client(), upstream.URL, "test-key")
	app := historyTestApp(handler, "user-123")
	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/history?page=2", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestGetHistoryUnauthenticatedReturns401(t *testing.T) {
	handler := NewExamHandler(http.DefaultClient, "http://unused", "test-key")
	app := fiber.New()
	app.Get("/history", handler.GetHistory)
	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/history", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.StatusCode)
	}
}

func TestGetWeakAreasUsesAuthenticatedUser(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/users/user-123/weak-areas" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.Header.Get("X-Internal-API-Key"); got != "test-key" {
			t.Fatalf("expected internal API key, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer upstream.Close()

	handler := NewExamHandler(upstream.Client(), upstream.URL, "test-key")
	app := historyTestApp(handler, "user-123")
	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/weak-areas", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func historyTestApp(handler *ExamHandler, userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, userID)
		return c.Next()
	})
	app.Get("/history", handler.GetHistory)
	app.Get("/weak-areas", handler.GetWeakAreas)
	return app
}
