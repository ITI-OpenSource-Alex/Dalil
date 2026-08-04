package handlers

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func profileTestApp(handler *ProfileHandler, userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, userID)
		return c.Next()
	})
	app.Get("/profile", handler.GetProfile)
	return app
}

func TestGetProfileForwardsJWTUserIDAndInternalKey(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/users/user-123" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.Header.Get("X-Internal-Api-Key"); got != "test-internal-key" {
			t.Fatalf("expected internal key forwarded, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"user-123","email":"a@example.com"}`))
	}))
	defer upstream.Close()

	handler := NewProfileHandler(upstream.Client(), upstream.URL, "test-internal-key")
	app := profileTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/profile", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestGetProfileUnauthenticatedReturns401(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("upstream must not be called without an authenticated user")
	}))
	defer upstream.Close()

	handler := NewProfileHandler(upstream.Client(), upstream.URL, "test-internal-key")
	app := fiber.New()
	app.Get("/profile", handler.GetProfile) // no JWT middleware installed

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/profile", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.StatusCode)
	}
}

func TestGetProfileNeverUsesClientSuppliedID(t *testing.T) {
	// There is no client-controlled id input on this route at all (unlike
	// checklist's X-User-ID override test) -- this pins that the upstream path is
	// always built from the JWT-authenticated id, never anything from the request.
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/users/actual-jwt-user" {
			t.Fatalf("expected the JWT-authenticated user's id in the path, got %q", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	handler := NewProfileHandler(upstream.Client(), upstream.URL, "test-internal-key")
	app := profileTestApp(handler, "actual-jwt-user")

	request := httptest.NewRequest(http.MethodGet, "/profile?id=someone-else", nil)
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestGetProfilePropagatesUpstream404(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"message":"User with ID user-123 not found"}`))
	}))
	defer upstream.Close()

	handler := NewProfileHandler(upstream.Client(), upstream.URL, "test-internal-key")
	app := profileTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/profile", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 propagated from the user service, got %d", response.StatusCode)
	}
}

func TestGetProfileUpstreamUnreachableReturns502(t *testing.T) {
	handler := NewProfileHandler(http.DefaultClient, "http://127.0.0.1:0", "test-internal-key")
	app := profileTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/profile", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusBadGateway {
		t.Fatalf("expected 502 when the user service is unreachable, got %d", response.StatusCode)
	}
}
