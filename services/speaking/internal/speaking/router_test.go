package speaking

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
)

// buildTestRouter constructs the production routing table. The WebSocket and
// holistic-evaluation routes capture their clients lazily, so nil clients are
// safe here: these tests only exercise the /sessions* and /metrics routes.
func buildTestRouter(t *testing.T, repo db.Repository) *http.ServeMux {
	t.Helper()

	defer func() {
		// net/http panics at registration time — not on first request — when
		// two patterns are ambiguous. Converting that panic into a readable
		// failure is the whole point of this guard: without it the regression
		// only shows up as a crash loop after deploy.
		if r := recover(); r != nil {
			t.Fatalf("NewRouter panicked while registering routes: %v", r)
		}
	}()

	return NewRouter(RouterDeps{
		Config: &Config{},
		Repo:   repo,
	})
}

// TestNewRouter_RegistersWithoutPanic is the startup regression guard. It fails
// if anyone reintroduces conflicting route patterns (the defect that made the
// service panic on boot while its container still reported healthy).
func TestNewRouter_RegistersWithoutPanic(t *testing.T) {
	if got := buildTestRouter(t, &sessionsMockRepo{}); got == nil {
		t.Fatal("NewRouter returned nil")
	}
}

// TestNewRouter_PreflightRoutes covers every /sessions* path the browser sends
// a CORS preflight to. "/sessions/public/share" is included deliberately: it is
// the exact path that made "OPTIONS /sessions/{id}/share" and
// "OPTIONS /sessions/public/{token}" ambiguous, so it must stay routable.
func TestNewRouter_PreflightRoutes(t *testing.T) {
	mux := buildTestRouter(t, &sessionsMockRepo{})

	paths := []string{
		"/sessions",
		"/sessions/3f2504e0-4f89-11d3-9a0c-0305e82c3301",
		"/sessions/3f2504e0-4f89-11d3-9a0c-0305e82c3301/share",
		"/sessions/public/abc123token",
		"/sessions/public/share",
	}

	for _, path := range paths {
		t.Run(path, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodOptions, path, nil)
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusNoContent {
				t.Errorf("expected 204 for OPTIONS %s, got %d", path, rec.Code)
			}
			if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "*" {
				t.Errorf("expected CORS origin header for OPTIONS %s, got %q", path, got)
			}
		})
	}
}

// TestNewRouter_DispatchesToHandlers proves the router wires each method+path
// to the right handler, so the preflight wildcard hasn't shadowed a real route.
func TestNewRouter_DispatchesToHandlers(t *testing.T) {
	const sessionID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"

	repo := &sessionsMockRepo{
		listByUserFn: func(ctx context.Context, userID string) ([]*db.SpeakingSessionSummary, error) {
			return []*db.SpeakingSessionSummary{{ID: sessionID}}, nil
		},
		getByIDFn: func(ctx context.Context, id string) (*db.SpeakingSession, error) {
			return &db.SpeakingSession{ID: id, UserID: "user-lina"}, nil
		},
		createShareTokenFn: func(ctx context.Context, id string) (string, error) {
			return "sharetoken", nil
		},
		getByShareTokenFn: func(ctx context.Context, token string) (*db.SpeakingSession, error) {
			return &db.SpeakingSession{ID: sessionID, UserID: "user-lina"}, nil
		},
	}
	mux := buildTestRouter(t, repo)

	cases := []struct {
		name   string
		method string
		path   string
		want   int
	}{
		{"list", http.MethodGet, "/sessions?userId=user-lina", http.StatusOK},
		{"detail", http.MethodGet, "/sessions/" + sessionID + "?userId=user-lina", http.StatusOK},
		{"share", http.MethodPost, "/sessions/" + sessionID + "/share", http.StatusOK},
		{"public", http.MethodGet, "/sessions/public/sharetoken", http.StatusOK},
		{"list without userId", http.MethodGet, "/sessions", http.StatusBadRequest},
		{"malformed uuid", http.MethodGet, "/sessions/not-a-uuid", http.StatusNotFound},
		{"malformed uuid on share", http.MethodPost, "/sessions/not-a-uuid/share", http.StatusNotFound},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tc.want {
				t.Errorf("%s %s: expected %d, got %d (%s)", tc.method, tc.path, tc.want, rec.Code, rec.Body.String())
			}
		})
	}
}
