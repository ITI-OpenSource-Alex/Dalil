package handlers

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func TestListEssaysUsesAuthenticatedUserAndForwardsQueryParams(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/essays" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.URL.Query().Get("user_id"); got != "user-123" {
			t.Fatalf("expected authenticated user ID, got %q", got)
		}
		if got := r.URL.Query().Get("page"); got != "2" {
			t.Fatalf("expected page=2 forwarded, got %q", got)
		}
		if got := r.URL.Query().Get("submission_type"); got != "practice" {
			t.Fatalf("expected submission_type=practice forwarded, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[]`))
	}))
	defer upstream.Close()

	handler := NewWritingHandler(upstream.Client(), nil, upstream.URL)
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "user-123")
		return c.Next()
	})
	app.Get("/essays", handler.ListEssays)

	response, err := app.Test(httptest.NewRequest(
		http.MethodGet,
		"/essays?page=2&submission_type=practice",
		nil,
	))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestListEssaysUnauthenticatedReturns401(t *testing.T) {
	handler := NewWritingHandler(http.DefaultClient, nil, "http://unused")
	app := fiber.New()
	app.Get("/essays", handler.ListEssays)

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/essays", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.StatusCode)
	}
}

func TestListEssaysIgnoresClientSuppliedUserID(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("user_id"); got != "authenticated-user" {
			t.Fatalf("expected authenticated user ID to win, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[]`))
	}))
	defer upstream.Close()

	handler := NewWritingHandler(upstream.Client(), nil, upstream.URL)
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "authenticated-user")
		return c.Next()
	})
	app.Get("/essays", handler.ListEssays)

	response, err := app.Test(httptest.NewRequest(
		http.MethodGet,
		"/essays?user_id=someone-else",
		nil,
	))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}
