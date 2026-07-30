package middleware

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

const (
	ownerUserID    = "11111111-1111-1111-1111-111111111111"
	impostorUserID = "22222222-2222-2222-2222-222222222222"
	testSessionID  = "33333333-3333-3333-3333-333333333333"
)

type fakeExamOwnerStore struct {
	mu     sync.Mutex
	values map[string]string
	writes []cacheWrite
	getErr error
	setErr error
}

func newFakeExamOwnerStore() *fakeExamOwnerStore {
	return &fakeExamOwnerStore{values: map[string]string{}}
}

func (s *fakeExamOwnerStore) Get(_ context.Context, key string) *redis.StringCmd {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.getErr != nil {
		return redis.NewStringResult("", s.getErr)
	}
	value, ok := s.values[key]
	if !ok {
		return redis.NewStringResult("", redis.Nil)
	}
	return redis.NewStringResult(value, nil)
}

func (s *fakeExamOwnerStore) Set(
	_ context.Context,
	key string,
	value any,
	expiration time.Duration,
) *redis.StatusCmd {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.setErr != nil {
		return redis.NewStatusResult("", s.setErr)
	}
	stored, _ := value.(string)
	s.values[key] = stored
	s.writes = append(s.writes, cacheWrite{key: key, value: stored, ttl: expiration})
	return redis.NewStatusResult("OK", nil)
}

func (s *fakeExamOwnerStore) writeCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.writes)
}

// TestOwnershipMiddlewareRejectsWrongOwner is the DoD unit case: a session that
// belongs to somebody else must not be readable.
func TestOwnershipMiddlewareRejectsWrongOwner(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)
	app := examOwnershipTestApp(ownership, impostorUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected 403 for a session owned by another user, got %d", resp.StatusCode)
	}
}

// TestSubmitFromAnotherUserReturns403 is the DoD unit case for the submit verb
// specifically -- a wrong owner must be stopped before the answers reach the Exam
// service, not merely prevented from reading the score afterwards.
func TestSubmitFromAnotherUserReturns403(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)
	app := examOwnershipTestApp(ownership, impostorUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodPut, "/exam/sessions/"+testSessionID+"/submit")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected 403 submitting another user's session, got %d", resp.StatusCode)
	}
	if body := readOwnershipBody(t, resp); body["forwarded"] == true {
		t.Fatal("expected the request to be stopped before reaching the handler")
	}
}

func TestOwnershipMiddlewareAllowsTheOwner(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)
	app := examOwnershipTestApp(ownership, ownerUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodPut, "/exam/sessions/"+testSessionID+"/submit")
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected the owner to pass through, got %d", resp.StatusCode)
	}
}

func TestOwnershipResultIsCachedForFiveMinutes(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	store := newFakeExamOwnerStore()
	ownership := newTestExamOwnership(t, store, examService)
	app := examOwnershipTestApp(ownership, ownerUserID)

	for i := range 3 {
		resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
		if resp.StatusCode != fiber.StatusOK {
			t.Fatalf("request %d expected 200, got %d", i+1, resp.StatusCode)
		}
	}

	if got := calls.Load(); got != 1 {
		t.Fatalf("expected one exam service lookup for three requests, got %d", got)
	}
	if store.writeCount() != 1 {
		t.Fatalf("expected one cache write, got %d", store.writeCount())
	}
	write := store.writes[0]
	if write.key != ExamSessionOwnerCacheKey(testSessionID) ||
		write.value != ownerUserID ||
		write.ttl != 5*time.Minute {
		t.Fatalf("unexpected cache write: %#v", write)
	}
}

// A cached owner must gate the impostor too, otherwise the cache would only ever
// be consulted on the happy path and every rejection would cost a round trip.
func TestCachedOwnerRejectsImpostorWithoutUpstreamCall(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	store := newFakeExamOwnerStore()
	store.values[ExamSessionOwnerCacheKey(testSessionID)] = ownerUserID
	ownership := newTestExamOwnership(t, store, examService)
	app := examOwnershipTestApp(ownership, impostorUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected 403, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 0 {
		t.Fatalf("expected no exam service call on a cache hit, got %d", got)
	}
}

// A Redis outage must not lock a candidate out of their own exam: the middleware
// falls back to the authoritative lookup rather than failing closed.
func TestCacheReadErrorFallsBackToExamService(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	store := newFakeExamOwnerStore()
	store.getErr = errors.New("redis unavailable")
	ownership := newTestExamOwnership(t, store, examService)
	app := examOwnershipTestApp(ownership, ownerUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected the owner to pass through during a cache outage, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 1 {
		t.Fatalf("expected one exam service lookup, got %d", got)
	}
}

// The same outage must still reject an impostor -- degraded, never bypassed.
func TestCacheReadErrorStillRejectsWrongOwner(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	store := newFakeExamOwnerStore()
	store.getErr = errors.New("redis unavailable")
	ownership := newTestExamOwnership(t, store, examService)
	app := examOwnershipTestApp(ownership, impostorUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected 403 during a cache outage, got %d", resp.StatusCode)
	}
}

func TestCacheWriteErrorDoesNotFailTheRequest(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	store := newFakeExamOwnerStore()
	store.setErr = errors.New("redis unavailable")
	ownership := newTestExamOwnership(t, store, examService)
	app := examOwnershipTestApp(ownership, ownerUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected a cache write failure to be tolerated, got %d", resp.StatusCode)
	}
}

func TestUnknownSessionIsRelayedAsNotFound(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, "", http.StatusNotFound)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)
	app := examOwnershipTestApp(ownership, ownerUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusNotFound {
		t.Fatalf("expected 404 for an unknown session, got %d", resp.StatusCode)
	}
}

func TestUnreachableExamServiceIsRefusedNotAllowed(t *testing.T) {
	store := newFakeExamOwnerStore()
	ownership := NewExamSessionOwnership(
		store,
		&http.Client{Timeout: time.Second},
		// Reserved TEST-NET-1 address; nothing listens and the dial fails fast.
		"http://192.0.2.1:9",
		"test-internal-key",
		5*time.Minute,
		zerolog.Nop(),
	)
	app := examOwnershipTestApp(ownership, ownerUserID)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusBadGateway {
		t.Fatalf("expected 502 when the exam service is unreachable, got %d", resp.StatusCode)
	}
}

func TestValidateQueryReadsTheSessionIDFromTheQueryString(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)

	app := newExamWSTestApp(ownership, impostorUserID)
	resp := performOwnershipRequest(
		t, app, fiber.MethodGet, "/exam/speaking/ws?exam_session_id="+testSessionID,
	)
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected 403 for a query-supplied session owned by another user, got %d", resp.StatusCode)
	}
}

func TestMissingSessionIDIsRejected(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)

	app := newExamWSTestApp(ownership, ownerUserID)
	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/speaking/ws")
	if resp.StatusCode != fiber.StatusBadRequest {
		t.Fatalf("expected 400 without a session id, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 0 {
		t.Fatalf("expected no exam service call without a session id, got %d", got)
	}
}

func TestOwnershipRequiresAnAuthenticatedUser(t *testing.T) {
	var calls atomic.Int32
	examService := examOwnerServer(t, &calls, ownerUserID, http.StatusOK)
	ownership := newTestExamOwnership(t, newFakeExamOwnerStore(), examService)

	app := fiber.New()
	app.Get("/exam/sessions/:sessionId/result", ownership.Validate, ownershipTerminalHandler)

	resp := performOwnershipRequest(t, app, fiber.MethodGet, "/exam/sessions/"+testSessionID+"/result")
	if resp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected 401 without an authenticated user, got %d", resp.StatusCode)
	}
}

func newTestExamOwnership(
	t *testing.T,
	store ExamOwnerStore,
	examService *httptest.Server,
) *ExamSessionOwnership {
	t.Helper()
	return NewExamSessionOwnership(
		store,
		examService.Client(),
		examService.URL,
		"test-internal-key",
		5*time.Minute,
		zerolog.Nop(),
	)
}

func ownershipTerminalHandler(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{"forwarded": true})
}

// newOwnershipApp seeds the locals the real /api chain always provides: the
// authenticated user from the JWT middleware and the correlation id from
// RequestID. Omitting the latter is not cosmetic -- the Exam service stub rejects
// a call that arrives without one, exactly as a misconfigured chain would.
func newOwnershipApp(userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(ContextKeyUserID, userID)
		c.Locals(ContextKeyRequestID, "corr-1")
		return c.Next()
	})
	return app
}

func examOwnershipTestApp(ownership *ExamSessionOwnership, userID string) *fiber.App {
	app := newOwnershipApp(userID)
	app.Put("/exam/sessions/:sessionId/submit", ownership.Validate, ownershipTerminalHandler)
	app.Get("/exam/sessions/:sessionId/result", ownership.Validate, ownershipTerminalHandler)
	return app
}

func newExamWSTestApp(ownership *ExamSessionOwnership, userID string) *fiber.App {
	app := newOwnershipApp(userID)
	app.Get("/exam/speaking/ws", ownership.ValidateQuery("exam_session_id"), ownershipTerminalHandler)
	return app
}

func performOwnershipRequest(
	t *testing.T,
	app *fiber.App,
	method string,
	path string,
) *http.Response {
	t.Helper()
	resp, err := app.Test(httptest.NewRequest(method, path, nil), -1)
	if err != nil {
		t.Fatalf("perform request: %v", err)
	}
	t.Cleanup(func() { resp.Body.Close() })
	return resp
}

func readOwnershipBody(t *testing.T, resp *http.Response) map[string]any {
	t.Helper()
	payload := map[string]any{}
	// A fiber error response is not JSON, so a decode failure is not a test failure.
	_ = json.NewDecoder(resp.Body).Decode(&payload)
	return payload
}

// examOwnerServer stands in for the Exam service's
// GET /internal/sessions/{id}/owner endpoint and asserts the Gateway calls it the
// way that endpoint requires: exact path, and the internal API key its
// validate_internal_api_key dependency checks.
func examOwnerServer(
	t *testing.T,
	calls *atomic.Int32,
	ownerID string,
	status int,
) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/internal/sessions/"+testSessionID+"/owner" {
			http.Error(w, "unexpected path "+r.URL.Path, http.StatusNotFound)
			return
		}
		if r.Header.Get("X-Internal-API-Key") != "test-internal-key" {
			http.Error(w, "missing internal key", http.StatusUnauthorized)
			return
		}
		if r.Header.Get(HeaderCorrelationID) == "" {
			http.Error(w, "missing correlation id", http.StatusBadRequest)
			return
		}
		if status != http.StatusOK {
			http.Error(w, "session not found", status)
			return
		}
		w.Header().Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
		_ = json.NewEncoder(w).Encode(map[string]string{"user_id": ownerID})
	}))
	t.Cleanup(server.Close)
	return server
}
