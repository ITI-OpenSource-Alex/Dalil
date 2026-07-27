package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
)

// testSessionID is a syntactically valid UUID. The handlers reject malformed
// ids before querying, so tests that expect to reach the repository must use a
// parseable one.
const testSessionID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"

// sessionsMockRepo is a per-call-configurable mock satisfying db.Repository,
// used to exercise the sessions_handler.go HTTP handlers in isolation.
type sessionsMockRepo struct {
	listByUserFn       func(ctx context.Context, userID string) ([]*db.SpeakingSessionSummary, error)
	getByIDFn          func(ctx context.Context, id string) (*db.SpeakingSession, error)
	createShareTokenFn func(ctx context.Context, sessionID string) (string, error)
	getByShareTokenFn  func(ctx context.Context, token string) (*db.SpeakingSession, error)
}

func (m *sessionsMockRepo) Create(ctx context.Context, session *db.SpeakingSession) error {
	return nil
}

func (m *sessionsMockRepo) ListByUser(ctx context.Context, userID string) ([]*db.SpeakingSessionSummary, error) {
	return m.listByUserFn(ctx, userID)
}

func (m *sessionsMockRepo) GetByID(ctx context.Context, id string) (*db.SpeakingSession, error) {
	return m.getByIDFn(ctx, id)
}

func (m *sessionsMockRepo) CreateShareToken(ctx context.Context, sessionID string) (string, error) {
	return m.createShareTokenFn(ctx, sessionID)
}

func (m *sessionsMockRepo) GetByShareToken(ctx context.Context, token string) (*db.SpeakingSession, error) {
	return m.getByShareTokenFn(ctx, token)
}

func TestHandleListSessions_MissingUserID(t *testing.T) {
	repo := &sessionsMockRepo{}
	req := httptest.NewRequest(http.MethodGet, "/sessions", nil)
	rec := httptest.NewRecorder()

	HandleListSessions(rec, req, repo)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestHandleListSessions_Success(t *testing.T) {
	repo := &sessionsMockRepo{
		listByUserFn: func(ctx context.Context, userID string) ([]*db.SpeakingSessionSummary, error) {
			if userID != "user-lina" {
				t.Errorf("expected userID 'user-lina', got %q", userID)
			}
			return []*db.SpeakingSessionSummary{
				{ID: "s1", QuestionPrompt: "Describe a journey.", QuestionType: "part2", OverallBand: 7.0, CreatedAt: time.Now()},
			}, nil
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions?userId=user-lina", nil)
	rec := httptest.NewRecorder()

	HandleListSessions(rec, req, repo)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var got []sessionSummaryResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if len(got) != 1 || got[0].ID != "s1" || got[0].OverallBand != 7.0 {
		t.Errorf("unexpected response body: %+v", got)
	}
}

func TestHandleListSessions_RepoError(t *testing.T) {
	repo := &sessionsMockRepo{
		listByUserFn: func(ctx context.Context, userID string) ([]*db.SpeakingSessionSummary, error) {
			return nil, context.DeadlineExceeded
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions?userId=user-lina", nil)
	rec := httptest.NewRecorder()

	HandleListSessions(rec, req, repo)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", rec.Code)
	}
}

func TestHandleGetSession_NotFound(t *testing.T) {
	repo := &sessionsMockRepo{
		getByIDFn: func(ctx context.Context, id string) (*db.SpeakingSession, error) {
			return nil, db.ErrSessionNotFound
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions/"+testSessionID, nil)
	req.SetPathValue("id", testSessionID)
	rec := httptest.NewRecorder()

	HandleGetSession(rec, req, repo)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

// A malformed id must be rejected before it reaches the database — Postgres
// would otherwise fail the uuid cast and the handler would report 500 for what
// is really bad client input.
func TestHandleGetSession_MalformedUUIDIsNotFound(t *testing.T) {
	repo := &sessionsMockRepo{
		getByIDFn: func(ctx context.Context, id string) (*db.SpeakingSession, error) {
			t.Fatalf("repository must not be queried for malformed id %q", id)
			return nil, nil
		},
	}

	for _, id := range []string{"not-a-uuid", "123", "3f2504e0-4f89-11d3-9a0c"} {
		t.Run(id, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, "/sessions/"+id, nil)
			req.SetPathValue("id", id)
			rec := httptest.NewRecorder()

			HandleGetSession(rec, req, repo)

			if rec.Code != http.StatusNotFound {
				t.Fatalf("expected 404 for malformed id %q, got %d", id, rec.Code)
			}
		})
	}
}

func TestHandleGetSession_WrongUserTreatedAsNotFound(t *testing.T) {
	repo := &sessionsMockRepo{
		getByIDFn: func(ctx context.Context, id string) (*db.SpeakingSession, error) {
			return &db.SpeakingSession{ID: id, UserID: "someone-else"}, nil
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions/"+testSessionID+"?userId=user-lina", nil)
	req.SetPathValue("id", testSessionID)
	rec := httptest.NewRecorder()

	HandleGetSession(rec, req, repo)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for a session owned by a different user, got %d", rec.Code)
	}
}

func TestHandleGetSession_Success(t *testing.T) {
	repo := &sessionsMockRepo{
		getByIDFn: func(ctx context.Context, id string) (*db.SpeakingSession, error) {
			return &db.SpeakingSession{
				ID:             id,
				UserID:         "user-lina",
				QuestionPrompt: "Describe a book you read.",
				QuestionType:   "part2",
				Transcript:     "It was a great book...",
				Evaluation:     json.RawMessage(`{"Fluency and Coherence": {"band": 7.0}}`),
				OverallBand:    7.0,
				CreatedAt:      time.Now(),
			}, nil
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions/"+testSessionID+"?userId=user-lina", nil)
	req.SetPathValue("id", testSessionID)
	rec := httptest.NewRecorder()

	HandleGetSession(rec, req, repo)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var got sessionDetailResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if got.ID != testSessionID || got.Transcript != "It was a great book..." {
		t.Errorf("unexpected response body: %+v", got)
	}
	if strings.Contains(rec.Body.String(), "user_id") {
		t.Error("session detail response must not leak user_id")
	}
}

func TestHandleCreateShareLink_NotFound(t *testing.T) {
	repo := &sessionsMockRepo{
		createShareTokenFn: func(ctx context.Context, sessionID string) (string, error) {
			return "", db.ErrSessionNotFound
		},
	}

	req := httptest.NewRequest(http.MethodPost, "/sessions/"+testSessionID+"/share", nil)
	req.SetPathValue("id", testSessionID)
	rec := httptest.NewRecorder()

	HandleCreateShareLink(rec, req, repo)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

func TestHandleCreateShareLink_MalformedUUIDIsNotFound(t *testing.T) {
	repo := &sessionsMockRepo{
		createShareTokenFn: func(ctx context.Context, sessionID string) (string, error) {
			t.Fatalf("repository must not be queried for malformed id %q", sessionID)
			return "", nil
		},
	}

	req := httptest.NewRequest(http.MethodPost, "/sessions/not-a-uuid/share", nil)
	req.SetPathValue("id", "not-a-uuid")
	rec := httptest.NewRecorder()

	HandleCreateShareLink(rec, req, repo)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for malformed id, got %d", rec.Code)
	}
}

func TestHandleCreateShareLink_Success(t *testing.T) {
	repo := &sessionsMockRepo{
		createShareTokenFn: func(ctx context.Context, sessionID string) (string, error) {
			if sessionID != testSessionID {
				t.Errorf("expected sessionID %q, got %q", testSessionID, sessionID)
			}
			return "abc123token", nil
		},
	}

	req := httptest.NewRequest(http.MethodPost, "/sessions/"+testSessionID+"/share", nil)
	req.SetPathValue("id", testSessionID)
	rec := httptest.NewRecorder()

	HandleCreateShareLink(rec, req, repo)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var got map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if got["share_token"] != "abc123token" {
		t.Errorf("unexpected share_token: %+v", got)
	}
}

func TestHandleGetPublicSession_NotFound(t *testing.T) {
	repo := &sessionsMockRepo{
		getByShareTokenFn: func(ctx context.Context, token string) (*db.SpeakingSession, error) {
			return nil, db.ErrSessionNotFound
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions/public/unknown", nil)
	req.SetPathValue("token", "unknown")
	rec := httptest.NewRecorder()

	HandleGetPublicSession(rec, req, repo)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
}

func TestHandleGetPublicSession_Success_OmitsUserID(t *testing.T) {
	repo := &sessionsMockRepo{
		getByShareTokenFn: func(ctx context.Context, token string) (*db.SpeakingSession, error) {
			return &db.SpeakingSession{
				ID:             "s1",
				UserID:         "user-lina",
				QuestionPrompt: "Describe a book you read.",
				QuestionType:   "part2",
				Transcript:     "It was a great book...",
				Evaluation:     json.RawMessage(`{"Fluency and Coherence": {"band": 7.0}}`),
				OverallBand:    7.0,
				CreatedAt:      time.Now(),
			}, nil
		},
	}

	req := httptest.NewRequest(http.MethodGet, "/sessions/public/abc123token", nil)
	req.SetPathValue("token", "abc123token")
	rec := httptest.NewRecorder()

	HandleGetPublicSession(rec, req, repo)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	if strings.Contains(rec.Body.String(), "user_id") || strings.Contains(rec.Body.String(), "user-lina") {
		t.Errorf("public share response must never include user-identifying data, got: %s", rec.Body.String())
	}
}

func TestWithCORS_HandlesPreflight(t *testing.T) {
	called := false
	handler := WithCORS(func(w http.ResponseWriter, r *http.Request) {
		called = true
	})

	req := httptest.NewRequest(http.MethodOptions, "/sessions", nil)
	rec := httptest.NewRecorder()

	handler(rec, req)

	if called {
		t.Error("wrapped handler must not run for an OPTIONS preflight request")
	}
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204 for preflight, got %d", rec.Code)
	}
	if rec.Header().Get("Access-Control-Allow-Origin") != "*" {
		t.Errorf("expected Access-Control-Allow-Origin header, got %q", rec.Header().Get("Access-Control-Allow-Origin"))
	}
}
