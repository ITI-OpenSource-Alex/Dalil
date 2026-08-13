package handlers

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// capturedRequest records what actually reached the upstream service, which is
// the only place these assertions mean anything: a handler that validates the
// caller's userId but then forwards the caller's body has fixed nothing.
type capturedRequest struct {
	path   string
	query  string
	body   string
	header http.Header
}

func newCapturingUpstream(t *testing.T, status int, response string) (*httptest.Server, *capturedRequest) {
	t.Helper()
	captured := &capturedRequest{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		captured.path = r.URL.Path
		captured.query = r.URL.RawQuery
		captured.body = string(body)
		captured.header = r.Header.Clone()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(response))
	}))
	t.Cleanup(srv.Close)
	return srv, captured
}

// newAuthedApp mounts routes behind a stub that sets the same Locals
// middleware.JWT would, so the handlers can be tested without Redis.
func newAuthedApp(userID string, register func(*fiber.App)) *fiber.App {
	app := fiber.New(fiber.Config{DisableStartupMessage: true})
	app.Use(func(c *fiber.Ctx) error {
		if userID == "" {
			return fiber.NewError(fiber.StatusUnauthorized, "missing or invalid authorization token")
		}
		c.Locals(middleware.ContextKeyUserID, userID)
		c.Locals(middleware.ContextKeyRequestID, "corr-1")
		return c.Next()
	})
	register(app)
	return app
}

// TestSpeakingSessions_UserIDComesFromTokenNotQuery is the IDOR regression
// guard. Speaking scopes GET /sessions/{id} to a user only when a userId query
// parameter is supplied, and before this route existed the browser supplied it
// -- so a caller could read any user's transcript by editing or omitting it.
func TestSpeakingSessions_UserIDComesFromTokenNotQuery(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `{"id":"s1"}`)
	h := NewSpeakingHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("attacker", func(app *fiber.App) {
		app.Get("/api/speaking/sessions/:sessionId", h.GetSession)
	})

	// The caller explicitly asks for someone else's data.
	req := httptest.NewRequest(fiber.MethodGet, "/api/speaking/sessions/s1?userId=victim", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}

	if got := captured.query; !strings.Contains(got, "userId=attacker") {
		t.Errorf("upstream query = %q, want it scoped to the token's user", got)
	}
	if strings.Contains(captured.query, "victim") {
		t.Errorf("the caller-supplied userId reached the upstream: %q", captured.query)
	}
	if captured.path != "/sessions/s1" {
		t.Errorf("upstream path = %q, want /sessions/s1", captured.path)
	}
	if captured.header.Get("X-Internal-API-Key") != "internal-key" {
		t.Error("the internal API key was not attached; it must stay server-side and be added here")
	}
	if captured.header.Get(middleware.HeaderCorrelationID) != "corr-1" {
		t.Error("correlation ID was not forwarded to the speaking service")
	}
}

func TestSpeakingSessions_ListScopedToToken(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `[]`)
	h := NewSpeakingHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("user-1", func(app *fiber.App) {
		app.Get("/api/speaking/sessions", h.ListSessions)
	})

	resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/api/speaking/sessions?userId=someone-else", nil))
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	if !strings.Contains(captured.query, "userId=user-1") || strings.Contains(captured.query, "someone-else") {
		t.Errorf("upstream query = %q, want it scoped to the token's user only", captured.query)
	}
}

func TestSpeakingSessions_UnauthenticatedRejected(t *testing.T) {
	upstream, _ := newCapturingUpstream(t, 200, `{}`)
	h := NewSpeakingHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("", func(app *fiber.App) {
		app.Get("/api/speaking/sessions", h.ListSessions)
		app.Get("/api/speaking/sessions/:sessionId", h.GetSession)
	})

	for _, path := range []string{"/api/speaking/sessions", "/api/speaking/sessions/s1"} {
		resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, path, nil))
		if err != nil {
			t.Fatalf("%s: %v", path, err)
		}
		if resp.StatusCode != fiber.StatusUnauthorized {
			t.Errorf("%s status = %d, want 401", path, resp.StatusCode)
		}
	}
}

// TestSpeakingPublicShare_NeedsNoToken -- the recipient of a share link has no
// account, so this route is unauthenticated by design and must stay that way.
func TestSpeakingPublicShare_NeedsNoToken(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `{"id":"s1","overall_band":7}`)
	h := NewSpeakingHandler(upstream.Client(), upstream.URL, "internal-key")

	// Registered with NO auth middleware at all, matching server.go.
	app := fiber.New(fiber.Config{DisableStartupMessage: true})
	app.Get("/speaking/sessions/public/:token", h.GetPublicSession)

	resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/speaking/sessions/public/tok-123", nil))
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	if captured.path != "/sessions/public/tok-123" {
		t.Errorf("upstream path = %q", captured.path)
	}
	// No user scope may be invented here -- doing so would break the feature.
	if strings.Contains(captured.query, "userId") {
		t.Errorf("public share must not carry a userId: %q", captured.query)
	}
}

// TestOpportunities_ForgedBodyUserIDIgnored. RAG's MatchRequest is a single
// userId field, so forwarding the caller's body would forward the only thing
// that must not be caller-controlled. The handler builds the body instead, and
// this asserts what reached RAG rather than what the handler intended.
func TestOpportunities_ForgedBodyUserIDIgnored(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `{"programs":[]}`)
	h := NewOpportunitiesHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("attacker", func(app *fiber.App) {
		app.Post("/api/opportunities/query", h.Query)
	})

	req := httptest.NewRequest(fiber.MethodPost, "/api/opportunities/query",
		strings.NewReader(`{"userId":"victim","extra":"ignored"}`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}

	var forwarded map[string]any
	if err := json.Unmarshal([]byte(captured.body), &forwarded); err != nil {
		t.Fatalf("upstream body was not JSON (%q): %v", captured.body, err)
	}
	if forwarded["userId"] != "attacker" {
		t.Errorf("upstream userId = %v, want the token's subject", forwarded["userId"])
	}
	if _, leaked := forwarded["extra"]; leaked {
		t.Errorf("the caller's body reached RAG: %q", captured.body)
	}
	if captured.path != "/match" {
		t.Errorf("upstream path = %q, want /match", captured.path)
	}
}

func TestOpportunities_UnauthenticatedRejected(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `{}`)
	h := NewOpportunitiesHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("", func(app *fiber.App) {
		app.Post("/api/opportunities/query", h.Query)
	})

	resp, err := app.Test(httptest.NewRequest(fiber.MethodPost, "/api/opportunities/query", strings.NewReader(`{}`)))
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	if resp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", resp.StatusCode)
	}
	if captured.path != "" {
		t.Errorf("RAG was contacted for an unauthenticated request (path %q)", captured.path)
	}
}

func TestOpportunities_DetailScopesFitToAuthenticatedUser(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `{"programId":"program-1"}`)
	h := NewOpportunitiesHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("user-42", func(app *fiber.App) {
		app.Get("/api/opportunities/:programId", h.Detail)
	})

	resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/api/opportunities/program-1", nil))
	if err != nil || resp.StatusCode != fiber.StatusOK {
		t.Fatalf("detail request: status=%d err=%v", resp.StatusCode, err)
	}
	if captured.path != "/programs/program-1" || captured.query != "userId=user-42" {
		t.Fatalf("upstream = %s?%s", captured.path, captured.query)
	}
}

// TestOpportunities_ForwardsTraceparent keeps RAG's Langfuse spans attached to
// the caller's trace instead of orphaning them behind the Gateway.
func TestOpportunities_ForwardsTraceparent(t *testing.T) {
	upstream, captured := newCapturingUpstream(t, 200, `{"programs":[]}`)
	h := NewOpportunitiesHandler(upstream.Client(), upstream.URL, "internal-key")
	app := newAuthedApp("user-1", func(app *fiber.App) {
		app.Post("/api/opportunities/query", h.Query)
	})

	req := httptest.NewRequest(fiber.MethodPost, "/api/opportunities/query", strings.NewReader(`{}`))
	req.Header.Set("traceparent", "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
	if _, err := app.Test(req); err != nil {
		t.Fatalf("request: %v", err)
	}
	if got := captured.header.Get("traceparent"); got == "" {
		t.Error("traceparent was dropped; RAG's spans would be orphaned")
	}
}
