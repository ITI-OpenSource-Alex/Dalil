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

type cacheWrite struct {
	key   string
	value string
	ttl   time.Duration
}

type fakeSubscriptionCache struct {
	mu      sync.Mutex
	values  map[string]string
	getErr  error
	setErr  error
	writes  []cacheWrite
	getHook func()
}

func (c *fakeSubscriptionCache) Get(_ context.Context, key string) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.getHook != nil {
		c.getHook()
	}
	if c.getErr != nil {
		return "", c.getErr
	}
	value, ok := c.values[key]
	if !ok {
		return "", redis.Nil
	}
	return value, nil
}

func (c *fakeSubscriptionCache) Set(
	_ context.Context,
	key string,
	value string,
	ttl time.Duration,
) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.setErr != nil {
		return c.setErr
	}
	c.values[key] = value
	c.writes = append(c.writes, cacheWrite{key: key, value: value, ttl: ttl})
	return nil
}

func TestFreeUserIsBlockedFromPaidRouteWithExactContract(t *testing.T) {
	cache := &fakeSubscriptionCache{
		values: map[string]string{SubscriptionCacheKey("user-1"): "free"},
	}
	subscriptions := newTestSubscriptionMiddleware(t, cache, nil)
	app := subscriptionTestApp(subscriptions, true)

	resp := performSubscriptionRequest(t, app, "/paid")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected 403, got %d", resp.StatusCode)
	}

	var payload map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(payload) != 2 ||
		payload["error"] != "subscription_required" ||
		payload["upgradeUrl"] != "https://goa.test/upgrade" {
		t.Fatalf("unexpected subscription response: %#v", payload)
	}
}

func TestPaidUserPassesThroughPaidRoute(t *testing.T) {
	cache := &fakeSubscriptionCache{
		values: map[string]string{SubscriptionCacheKey("user-1"): "paid"},
	}
	subscriptions := newTestSubscriptionMiddleware(t, cache, nil)
	app := subscriptionTestApp(subscriptions, true)

	resp := performSubscriptionRequest(t, app, "/paid")
	if resp.StatusCode != fiber.StatusNoContent {
		t.Fatalf("expected 204, got %d", resp.StatusCode)
	}
}

func TestCacheHitAvoidsUserServiceCall(t *testing.T) {
	var calls atomic.Int32
	userService := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		http.Error(w, "must not be called", http.StatusInternalServerError)
	}))
	t.Cleanup(userService.Close)

	cache := &fakeSubscriptionCache{
		values: map[string]string{SubscriptionCacheKey("user-1"): "paid"},
	}
	subscriptions := newTestSubscriptionMiddleware(t, cache, userService)
	app := subscriptionTestApp(subscriptions, true)

	resp := performSubscriptionRequest(t, app, "/paid")
	if resp.StatusCode != fiber.StatusNoContent {
		t.Fatalf("expected 204, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 0 {
		t.Fatalf("expected zero User service calls, got %d", got)
	}
}

func TestCacheMissCallsUserOnceAndWritesFiveMinuteTTL(t *testing.T) {
	var calls atomic.Int32
	userService := subscriptionUserServer(t, &calls, "paid", 0)
	cache := &fakeSubscriptionCache{values: map[string]string{}}
	subscriptions := newTestSubscriptionMiddleware(t, cache, userService)
	app := subscriptionTestApp(subscriptions, true)

	resp := performSubscriptionRequest(t, app, "/paid")
	if resp.StatusCode != fiber.StatusNoContent {
		t.Fatalf("expected 204, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 1 {
		t.Fatalf("expected one User service call, got %d", got)
	}
	if len(cache.writes) != 1 {
		t.Fatalf("expected one cache write, got %d", len(cache.writes))
	}
	write := cache.writes[0]
	if write.key != SubscriptionCacheKey("user-1") ||
		write.value != "paid" ||
		write.ttl != 5*time.Minute {
		t.Fatalf("unexpected cache write: %#v", write)
	}
}

func TestFiveConcurrentRequestsShareOneUserServiceLookup(t *testing.T) {
	var calls atomic.Int32
	userService := subscriptionUserServer(t, &calls, "paid", 50*time.Millisecond)
	cache := &fakeSubscriptionCache{values: map[string]string{}}
	subscriptions := newTestSubscriptionMiddleware(t, cache, userService)
	app := subscriptionTestApp(subscriptions, true)

	var wg sync.WaitGroup
	errs := make(chan error, 5)
	for range 5 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/paid", nil), -1)
			if err != nil {
				errs <- err
				return
			}
			defer resp.Body.Close()
			if resp.StatusCode != fiber.StatusNoContent {
				errs <- errors.New("paid route did not pass through")
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Error(err)
	}
	if got := calls.Load(); got != 1 {
		t.Fatalf("expected one User service call for five requests, got %d", got)
	}
}

func TestRedisReadErrorFailsClosedWithoutCallingUserService(t *testing.T) {
	var calls atomic.Int32
	userService := subscriptionUserServer(t, &calls, "paid", 0)
	cache := &fakeSubscriptionCache{
		values: map[string]string{},
		getErr: errors.New("redis unavailable"),
	}
	subscriptions := newTestSubscriptionMiddleware(t, cache, userService)
	app := subscriptionTestApp(subscriptions, true)

	resp := performSubscriptionRequest(t, app, "/paid")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected fail-closed 403, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 0 {
		t.Fatalf("expected no User service call after Redis error, got %d", got)
	}
}

func TestRedisWriteErrorFailsClosed(t *testing.T) {
	var calls atomic.Int32
	userService := subscriptionUserServer(t, &calls, "paid", 0)
	cache := &fakeSubscriptionCache{
		values: map[string]string{},
		setErr: errors.New("redis unavailable"),
	}
	subscriptions := newTestSubscriptionMiddleware(t, cache, userService)
	app := subscriptionTestApp(subscriptions, true)

	resp := performSubscriptionRequest(t, app, "/paid")
	if resp.StatusCode != fiber.StatusForbidden {
		t.Fatalf("expected fail-closed 403, got %d", resp.StatusCode)
	}
	if got := calls.Load(); got != 1 {
		t.Fatalf("expected one User service call before cache write failed, got %d", got)
	}
}

func TestFreeTierRouteIsNotBlocked(t *testing.T) {
	cache := &fakeSubscriptionCache{
		values: map[string]string{SubscriptionCacheKey("user-1"): "free"},
	}
	subscriptions := newTestSubscriptionMiddleware(t, cache, nil)
	app := subscriptionTestApp(subscriptions, false)

	resp := performSubscriptionRequest(t, app, "/free")
	if resp.StatusCode != fiber.StatusNoContent {
		t.Fatalf("expected free route to pass through, got %d", resp.StatusCode)
	}
}

func newTestSubscriptionMiddleware(
	t *testing.T,
	cache subscriptionCache,
	userService *httptest.Server,
) *SubscriptionMiddleware {
	t.Helper()
	userServiceURL := "http://unused.test"
	if userService != nil {
		userServiceURL = userService.URL
	}
	return &SubscriptionMiddleware{
		cache:          cache,
		httpClient:     http.DefaultClient,
		userServiceURL: userServiceURL,
		internalAPIKey: "test-internal-key",
		upgradeURL:     "https://goa.test/upgrade",
		cacheTTL:       5 * time.Minute,
		logger:         zerolog.Nop(),
	}
}

func subscriptionTestApp(subscriptions *SubscriptionMiddleware, paidRoute bool) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(ContextKeyUserID, "user-1")
		c.Locals(ContextKeyRequestID, "corr-1")
		return c.Next()
	})
	app.Use(subscriptions.ResolveSubscription)
	if paidRoute {
		app.Get("/paid", subscriptions.RequirePaid, func(c *fiber.Ctx) error {
			return c.SendStatus(fiber.StatusNoContent)
		})
	} else {
		app.Get("/free", func(c *fiber.Ctx) error {
			return c.SendStatus(fiber.StatusNoContent)
		})
	}
	return app
}

func performSubscriptionRequest(t *testing.T, app *fiber.App, path string) *http.Response {
	t.Helper()
	resp, err := app.Test(httptest.NewRequest(http.MethodGet, path, nil), -1)
	if err != nil {
		t.Fatalf("perform request: %v", err)
	}
	t.Cleanup(func() { resp.Body.Close() })
	return resp
}

func subscriptionUserServer(
	t *testing.T,
	calls *atomic.Int32,
	tier string,
	delay time.Duration,
) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/users/user-1/subscription" {
			http.Error(w, "unexpected path", http.StatusNotFound)
			return
		}
		if r.Header.Get("X-Internal-API-Key") != "test-internal-key" {
			http.Error(w, "missing internal key", http.StatusUnauthorized)
			return
		}
		if r.Header.Get(HeaderCorrelationID) != "corr-1" {
			http.Error(w, "missing correlation id", http.StatusBadRequest)
			return
		}
		if delay > 0 {
			time.Sleep(delay)
		}
		w.Header().Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
		_ = json.NewEncoder(w).Encode(map[string]string{"subscriptionTier": tier})
	}))
	t.Cleanup(server.Close)
	return server
}
