package handlers

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func checklistTestApp(handler *ChecklistHandler, userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, userID)
		return c.Next()
	})
	app.Get("/checklists/:programId", handler.GetChecklist)
	app.Put("/checklists/:programId/items/:itemId", handler.UpdateChecklistItem)
	app.Get("/checklists/:programId/financial", handler.GetChecklistFinancials)
	return app
}

func TestGetChecklistForwardsXUserIDFromJWT(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/checklists/prog-1" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.Header.Get("X-User-ID"); got != "user-123" {
			t.Fatalf("expected X-User-ID forwarded from the JWT, got %q", got)
		}
		// The RAG route takes no internal API key -- ownership is X-User-ID
		// alone (GOA-084). Confirm the gateway does not add one.
		if got := r.Header.Get("X-Internal-API-Key"); got != "" {
			t.Fatalf("expected no internal API key on the checklist route, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"checklistId":"c-1","programId":"prog-1","generatedBy":"llm","items":[]}`))
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/prog-1", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestGetChecklistUnauthenticatedReturns401(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("upstream must not be called without an authenticated user")
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := fiber.New()
	app.Get("/checklists/:programId", handler.GetChecklist) // no JWT middleware installed

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/prog-1", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.StatusCode)
	}
}

func TestGetChecklistPropagatesUpstream404(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Program not found"}`))
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/unknown-prog", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 propagated from the RAG service, got %d", response.StatusCode)
	}
}

func TestGetChecklistUpstreamUnreachableReturns502(t *testing.T) {
	handler := NewChecklistHandler(http.DefaultClient, "http://127.0.0.1:0")
	app := checklistTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/prog-1", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusBadGateway {
		t.Fatalf("expected 502 when the rag service is unreachable, got %d", response.StatusCode)
	}
}

func TestUpdateChecklistItemForwardsBodyAndUserID(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/checklists/prog-1/items/ielts_retake" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.Header.Get("X-User-ID"); got != "user-123" {
			t.Fatalf("expected X-User-ID forwarded from the JWT, got %q", got)
		}
		if got := r.Header.Get("Content-Type"); got != "application/json" {
			t.Fatalf("expected Content-Type forwarded, got %q", got)
		}
		body := make([]byte, r.ContentLength)
		_, _ = r.Body.Read(body)
		if !strings.Contains(string(body), `"checked":true`) {
			t.Fatalf("expected request body forwarded, got %q", string(body))
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"itemId":"ielts_retake","title":"Retake IELTS","checked":true}`))
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "user-123")

	request := httptest.NewRequest(
		http.MethodPut,
		"/checklists/prog-1/items/ielts_retake",
		strings.NewReader(`{"checked":true}`),
	)
	request.Header.Set("Content-Type", "application/json")
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestUpdateChecklistItemDifferentUserCannotImpersonate(t *testing.T) {
	// The gateway must source X-User-ID from the JWT, not from anything the
	// client sends -- there is no client-controlled field that could override it
	// here, but this pins that behavior against regression.
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("X-User-ID"); got != "actual-jwt-user" {
			t.Fatalf("expected the JWT-authenticated user, got %q", got)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "actual-jwt-user")

	request := httptest.NewRequest(
		http.MethodPut,
		"/checklists/prog-1/items/ielts_retake",
		strings.NewReader(`{"checked":true}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-User-ID", "someone-else") // must be ignored/overwritten
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

// GOA-035: GET /checklists/:programId/financial. Same forwarding/ownership shape as
// GetChecklist -- these tests only pin the extra path segment and that no internal
// API key is added (RAG's /financial route sits on the same require_user_id-scoped
// router as /checklists/:programId).

func TestGetChecklistFinancialsForwardsXUserIDFromJWT(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/checklists/prog-1/financial" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		if got := r.Header.Get("X-User-ID"); got != "user-123" {
			t.Fatalf("expected X-User-ID forwarded from the JWT, got %q", got)
		}
		if got := r.Header.Get("X-Internal-API-Key"); got != "" {
			t.Fatalf("expected no internal API key on the financial route, got %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"programId":"prog-1","items":[]}`))
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/prog-1/financial", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
}

func TestGetChecklistFinancialsUnauthenticatedReturns401(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("upstream must not be called without an authenticated user")
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := fiber.New()
	app.Get("/checklists/:programId/financial", handler.GetChecklistFinancials) // no JWT middleware

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/prog-1/financial", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.StatusCode)
	}
}

func TestGetChecklistFinancialsPropagatesUpstream404(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Program not found"}`))
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/unknown-prog/financial", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 propagated from the RAG service, got %d", response.StatusCode)
	}
}

func TestGetChecklistFinancialsDoesNotHitTheChecklistRoute(t *testing.T) {
	// Pins that GET /checklists/:programId/financial and GET /checklists/:programId
	// route to distinct handlers rather than the financial suffix being swallowed
	// into the programId parameter.
	var hitPath string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hitPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"programId":"prog-1","items":[]}`))
	}))
	defer upstream.Close()

	handler := NewChecklistHandler(upstream.Client(), upstream.URL)
	app := checklistTestApp(handler, "user-123")

	response, err := app.Test(httptest.NewRequest(http.MethodGet, "/checklists/prog-1/financial", nil))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if hitPath != "/checklists/prog-1/financial" {
		t.Fatalf("expected the financial route to be hit, got upstream path %q", hitPath)
	}
}
