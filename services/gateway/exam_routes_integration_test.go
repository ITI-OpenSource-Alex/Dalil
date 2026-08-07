package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/handlers"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

// TestFourthExamStartInTheSameHourReturns429 is the DoD integration case. It runs
// against real Redis so the counter, its hour window and its TTL are the real
// ones rather than a fake's approximation of them.
func TestFourthExamStartInTheSameHourReturns429(t *testing.T) {
	fixture := newExamRoutesFixture(t, "paid")

	for i := range 3 {
		status := fixture.request(t, fiber.MethodPost, "/api/exam/sessions")
		if status != fiber.StatusOK {
			t.Fatalf("exam start %d expected 200, got %d", i+1, status)
		}
	}

	if status := fixture.request(t, fiber.MethodPost, "/api/exam/sessions"); status != fiber.StatusTooManyRequests {
		t.Fatalf("expected the 4th exam start in the hour to return 429, got %d", status)
	}

	// The counter must be the key the ticket specifies, in the hour bucket.
	key := "exam_start:" + fixture.userID + ":" + time.Now().UTC().Format("2006-01-02T15")
	count, err := fixture.redis.Get(t.Context(), key).Int64()
	if err != nil {
		t.Fatalf("expected a counter at %q: %v", key, err)
	}
	if count != 4 {
		t.Fatalf("expected the counter to have recorded 4 attempts, got %d", count)
	}
	ttl, err := fixture.redis.TTL(t.Context(), key).Result()
	if err != nil {
		t.Fatalf("read counter TTL: %v", err)
	}
	if ttl <= 0 || ttl > time.Hour {
		t.Fatalf("expected a TTL inside the hour window, got %s", ttl)
	}
}

// A free-tier candidate must not reach any exam route, and must be told why.
func TestFreeTierIsBlockedFromExamRoutes(t *testing.T) {
	fixture := newExamRoutesFixture(t, "free")

	for _, route := range []struct {
		method string
		path   string
	}{
		{fiber.MethodPost, "/api/exam/sessions"},
		{fiber.MethodGet, "/api/exam/listening/start"},
		{fiber.MethodGet, "/api/exam/sessions/" + examOwnerSessionID + "/result"},
		{fiber.MethodPut, "/api/exam/sessions/" + examOwnerSessionID + "/submit"},
	} {
		if status := fixture.request(t, route.method, route.path); status != fiber.StatusForbidden {
			t.Fatalf("expected %s %s to be 403 for a free user, got %d", route.method, route.path, status)
		}
	}

	if got := fixture.examCalls.Load(); got != 0 {
		t.Fatalf("expected no exam service traffic from a free user, got %d calls", got)
	}
}

// Ownership is enforced end-to-end through the real middleware chain, and the
// rejection happens before the Exam service is asked to submit anything.
func TestSubmitFromAnotherUserIsRejectedEndToEnd(t *testing.T) {
	fixture := newExamRoutesFixture(t, "paid")

	status := fixture.request(t, fiber.MethodPut, "/api/exam/sessions/"+foreignSessionID+"/submit")
	if status != fiber.StatusForbidden {
		t.Fatalf("expected 403 submitting another user's session, got %d", status)
	}
	if got := fixture.submitCalls.Load(); got != 0 {
		t.Fatalf("expected the submit never to reach the exam service, got %d calls", got)
	}
}

func TestOwnerReachesSubmitAndResult(t *testing.T) {
	fixture := newExamRoutesFixture(t, "paid")

	if status := fixture.request(t, fiber.MethodPut, "/api/exam/sessions/"+examOwnerSessionID+"/submit"); status != fiber.StatusOK {
		t.Fatalf("expected the owner's submit to pass through, got %d", status)
	}
	if status := fixture.request(t, fiber.MethodGet, "/api/exam/sessions/"+examOwnerSessionID+"/result"); status != fiber.StatusOK {
		t.Fatalf("expected the owner's result to pass through, got %d", status)
	}

	// Ownership was resolved once and cached for the second request.
	if got := fixture.ownerCalls.Load(); got != 1 {
		t.Fatalf("expected one owner lookup across two requests, got %d", got)
	}
	key := middleware.ExamSessionOwnerCacheKey(examOwnerSessionID)
	ttl, err := fixture.redis.TTL(t.Context(), key).Result()
	if err != nil {
		t.Fatalf("read ownership cache TTL: %v", err)
	}
	if ttl <= 0 || ttl > 5*time.Minute {
		t.Fatalf("expected the ownership cache to hold a 5 minute TTL, got %s", ttl)
	}
}

const (
	examOwnerSessionID = "66666666-6666-6666-6666-666666666666"
	foreignSessionID   = "77777777-7777-7777-7777-777777777777"
	otherUserID        = "88888888-8888-8888-8888-888888888888"
)

type examRoutesFixture struct {
	app         *fiber.App
	redis       *redis.Client
	userID      string
	accessToken string
	examCalls   *atomic.Int32
	ownerCalls  *atomic.Int32
	submitCalls *atomic.Int32
}

func (f *examRoutesFixture) request(t *testing.T, method string, path string) int {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	req.Header.Set(fiber.HeaderAuthorization, "Bearer "+f.accessToken)
	resp, err := f.app.Test(req, -1)
	if err != nil {
		t.Fatalf("%s %s returned error: %v", method, path, err)
	}
	t.Cleanup(func() { resp.Body.Close() })
	return resp.StatusCode
}

// newExamRoutesFixture assembles the exam prep chain exactly as NewGatewayServer
// does -- JWT, the generic limiter, subscription resolution, then the paid-tier
// exam group with the start limiter and ownership middleware. The upstreams are
// stubbed but the middleware and Redis are real, which is where the behaviour
// under test actually lives.
func newExamRoutesFixture(t *testing.T, tier string) *examRoutesFixture {
	t.Helper()
	useIsolatedPrometheusRegistry(t)

	metrics, err := observability.NewMetrics()
	if err != nil {
		t.Fatalf("NewMetrics returned error: %v", err)
	}
	logger := zerolog.Nop()

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://127.0.0.1:6379/0"
	}
	redisOpts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("failed to parse redis url: %v", err)
	}
	redisClient := redis.NewClient(redisOpts)
	t.Cleanup(func() { _ = redisClient.Close() })
	if err := redisClient.Ping(t.Context()).Err(); err != nil {
		t.Skipf("Redis integration dependency unavailable: %v", err)
	}

	// A fresh user id per run keeps the hourly counter and the tier cache from
	// leaking between tests and between reruns inside the same clock hour.
	userID := uuid.NewString()
	t.Cleanup(func() {
		_ = redisClient.Del(
			t.Context(),
			"exam_start:"+userID+":"+time.Now().UTC().Format("2006-01-02T15"),
			middleware.SubscriptionCacheKey(userID),
			middleware.ExamSessionOwnerCacheKey(examOwnerSessionID),
			middleware.ExamSessionOwnerCacheKey(foreignSessionID),
		).Err()
	})
	// Ownership entries are keyed by session, which is shared across tests, so
	// clear them before the run too.
	_ = redisClient.Del(
		t.Context(),
		middleware.ExamSessionOwnerCacheKey(examOwnerSessionID),
		middleware.ExamSessionOwnerCacheKey(foreignSessionID),
	).Err()

	var examCalls, ownerCalls, submitCalls atomic.Int32
	examService := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		examCalls.Add(1)
		w.Header().Set("Content-Type", "application/json")

		if strings.HasSuffix(r.URL.Path, "/owner") {
			ownerCalls.Add(1)
			owner := userID
			if strings.Contains(r.URL.Path, foreignSessionID) {
				owner = otherUserID
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"user_id": owner})
			return
		}
		if strings.HasSuffix(r.URL.Path, "/submit") {
			submitCalls.Add(1)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	}))
	t.Cleanup(examService.Close)

	userService := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/users/"+userID+"/subscription" {
			http.Error(w, "unexpected path", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"subscriptionTier": tier})
	}))
	t.Cleanup(userService.Close)

	httpClient := &http.Client{Timeout: 10 * time.Second}
	examHandler := handlers.NewExamHandler(httpClient, examService.URL, "test-internal-key")
	subscriptions := middleware.NewSubscriptionMiddleware(
		redisClient, httpClient, userService.URL, "test-internal-key", "/upgrade", 5*time.Minute, logger,
	)
	ownership := middleware.NewExamSessionOwnership(
		redisClient, httpClient, examService.URL, "test-internal-key", 5*time.Minute, logger,
	)

	app := fiber.New(fiber.Config{ErrorHandler: middleware.ErrorHandler(logger)})
	app.Use(middleware.RequestID())
	api := app.Group("/api", middleware.JWT(testIntegrationJWTSecret, redisClient, metrics))
	api.Use(middleware.RateLimiter(redisClient, 60, metrics))
	api.Use(subscriptions.ResolveSubscription)

	exam := api.Group("/exam", subscriptions.RequirePaid)
	examStartLimiter := middleware.ExamStartRateLimiter(redisClient, 3, metrics)
	exam.Post("/sessions", examStartLimiter, examHandler.CreateSession)
	exam.Get("/listening/start", examStartLimiter, examHandler.StartListening)
	exam.Put("/sessions/:sessionId/submit", ownership.Validate, examHandler.SubmitSession)
	exam.Get("/sessions/:sessionId/result", ownership.Validate, examHandler.GetSessionResult)

	tokenService := gatewayauth.NewTokenService(testIntegrationJWTSecret, time.Hour, 24*time.Hour)
	accessToken, err := tokenService.NewAccessToken(gatewayauth.User{ID: userID, Email: "candidate@example.com"})
	if err != nil {
		t.Fatalf("mint access token: %v", err)
	}

	return &examRoutesFixture{
		app:         app,
		redis:       redisClient,
		userID:      userID,
		accessToken: accessToken,
		examCalls:   &examCalls,
		ownerCalls:  &ownerCalls,
		submitCalls: &submitCalls,
	}
}
