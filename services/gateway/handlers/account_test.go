package handlers

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// The account-deletion and data-export paths are authorised by the User
// service's UsersService.assertSelf(userId, requesterId), where requesterId is
// read from the x-user-id header. These tests exist because that header is the
// entire authorisation signal: forget it and every request is refused, forge it
// and one user can erase another.

func newAccountApp(t *testing.T, upstreamURL string, userID string) *fiber.App {
	t.Helper()

	handler := NewAuthHandler(nil, nil, nil, http.DefaultClient, upstreamURL, "internal-key")
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		if userID != "" {
			c.Locals(middleware.ContextKeyUserID, userID)
		}
		return c.Next()
	})
	app.Delete("/users/:id/account", handler.DeleteAccount)
	app.Get("/users/:id/data-export", handler.DataExport)
	return app
}

func TestDeleteAccountForwardsTheAuthenticatedUserAsXUserId(t *testing.T) {
	var seenHeader, seenPath, seenMethod string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenHeader = r.Header.Get("X-User-Id")
		seenPath = r.URL.Path
		seenMethod = r.Method
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"success":true}`))
	}))
	defer upstream.Close()

	app := newAccountApp(t, upstream.URL, "user-abc")
	req := httptest.NewRequest(http.MethodDelete, "/users/user-abc/account",
		strings.NewReader(`{"confirmPassword":"hunter2"}`))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
	if seenMethod != http.MethodDelete {
		t.Fatalf("expected DELETE upstream, got %q", seenMethod)
	}
	if seenPath != "/users/user-abc/account" {
		t.Fatalf("unexpected upstream path %q", seenPath)
	}
	// Without this header the User service sees an undefined requester and
	// assertSelf refuses every request -- the endpoint would be dead.
	if seenHeader != "user-abc" {
		t.Fatalf("x-user-id was not forwarded, got %q", seenHeader)
	}
}

func TestDataExportForwardsTheAuthenticatedUserAsXUserId(t *testing.T) {
	var seenHeader string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenHeader = r.Header.Get("X-User-Id")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"profile":{}}`))
	}))
	defer upstream.Close()

	app := newAccountApp(t, upstream.URL, "user-abc")
	resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/users/user-abc/data-export", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if seenHeader != "user-abc" {
		t.Fatalf("x-user-id was not forwarded, got %q", seenHeader)
	}
}

// The property that makes these endpoints safe to expose: the path names who is
// being acted on, the JWT names who is asking, and a mismatch is refused before
// the User service is ever contacted.
func TestOneUserCannotDeleteAnotherUsersAccount(t *testing.T) {
	called := false
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	app := newAccountApp(t, upstream.URL, "attacker")
	resp, err := app.Test(httptest.NewRequest(http.MethodDelete, "/users/victim/account", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", resp.StatusCode)
	}
	if called {
		t.Fatal("the User service was contacted for a cross-user deletion")
	}
}

func TestOneUserCannotExportAnotherUsersData(t *testing.T) {
	called := false
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	app := newAccountApp(t, upstream.URL, "attacker")
	resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/users/victim/data-export", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", resp.StatusCode)
	}
	if called {
		t.Fatal("the User service was contacted for a cross-user export")
	}
}

func TestAccountDeletionRequiresAuthentication(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("the User service was contacted for an unauthenticated request")
	}))
	defer upstream.Close()

	app := newAccountApp(t, upstream.URL, "")
	resp, err := app.Test(httptest.NewRequest(http.MethodDelete, "/users/anyone/account", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", resp.StatusCode)
	}
}

// A refusal from assertSelf must reach the caller as a refusal, not as a 200
// carrying an error body nobody reads.
func TestUpstreamRefusalIsRelayedNotSwallowed(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"message":"Forbidden resource"}`))
	}))
	defer upstream.Close()

	app := newAccountApp(t, upstream.URL, "user-abc")
	resp, err := app.Test(httptest.NewRequest(http.MethodDelete, "/users/user-abc/account", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("upstream 403 was not relayed; got %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Forbidden") {
		t.Fatalf("upstream body was not relayed: %s", body)
	}
}
