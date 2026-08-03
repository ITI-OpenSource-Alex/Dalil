package middleware

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

// fakeQuotaStore is a real counter with real TTLs, not a stub that returns
// whatever the test wants. The behaviour under test is "the Nth request is
// refused", and a store that cannot count cannot demonstrate it.
type fakeQuotaStore struct {
	counts map[string]int64
	ttls   map[string]time.Duration
	fail   bool
}

func newFakeQuotaStore() *fakeQuotaStore {
	return &fakeQuotaStore{counts: map[string]int64{}, ttls: map[string]time.Duration{}}
}

func (f *fakeQuotaStore) Incr(_ context.Context, key string) *redis.IntCmd {
	cmd := redis.NewIntCmd(context.Background())
	if f.fail {
		cmd.SetErr(errors.New("redis is down"))
		return cmd
	}
	f.counts[key]++
	cmd.SetVal(f.counts[key])
	return cmd
}

func (f *fakeQuotaStore) Expire(_ context.Context, key string, ttl time.Duration) *redis.BoolCmd {
	cmd := redis.NewBoolCmd(context.Background())
	if f.fail {
		cmd.SetErr(errors.New("redis is down"))
		return cmd
	}
	f.ttls[key] = ttl
	cmd.SetVal(true)
	return cmd
}

func (f *fakeQuotaStore) TTL(_ context.Context, key string) *redis.DurationCmd {
	cmd := redis.NewDurationCmd(context.Background(), time.Second)
	cmd.SetVal(f.ttls[key])
	return cmd
}

func newQuotaApp(store RateLimitStore, limit int, logs *bytes.Buffer) (*fiber.App, *int) {
	served := 0
	app := fiber.New()
	app.Post("/api/chat",
		func(c *fiber.Ctx) error {
			c.Locals(ContextKeyUserID, "user-123")
			c.Locals(ContextKeyRequestID, "corr-1")
			return c.Next()
		},
		AIRateLimiter(store, "chat", limit, time.Hour, zerolog.New(logs)),
		func(c *fiber.Ctx) error {
			served++
			return c.SendStatus(fiber.StatusOK)
		},
	)
	return app, &served
}

func fire(t *testing.T, app *fiber.App) *http.Response {
	t.Helper()
	resp, err := app.Test(httptest.NewRequest(http.MethodPost, "/api/chat", nil))
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

func TestRequestsWithinTheHourlyQuotaAreServed(t *testing.T) {
	var logs bytes.Buffer
	app, served := newQuotaApp(newFakeQuotaStore(), 3, &logs)

	for i := 0; i < 3; i++ {
		resp := fire(t, app)
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("request %d was refused with %d", i+1, resp.StatusCode)
		}
	}
	if *served != 3 {
		t.Fatalf("expected 3 requests served, got %d", *served)
	}
}

func TestTheRequestAfterTheQuotaIsRefusedBeforeTheModelCall(t *testing.T) {
	var logs bytes.Buffer
	app, served := newQuotaApp(newFakeQuotaStore(), 2, &logs)

	for i := 0; i < 2; i++ {
		fire(t, app).Body.Close()
	}
	resp := fire(t, app)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("expected 429, got %d", resp.StatusCode)
	}
	// The point of the control: the spend never happened.
	if *served != 2 {
		t.Fatalf("a refused request still reached the handler (served=%d)", *served)
	}
	if resp.Header.Get("Retry-After") == "" {
		t.Error("a refusal must tell the client when to come back")
	}
}

func TestTheWindowIsAnHourNotAMinute(t *testing.T) {
	store := newFakeQuotaStore()
	var logs bytes.Buffer
	app, _ := newQuotaApp(store, 5, &logs)

	fire(t, app).Body.Close()

	for _, ttl := range store.ttls {
		if ttl != time.Hour {
			t.Fatalf("expected an hour-long window, got %s", ttl)
		}
	}
}

// Zero is how the E2E suite and the load test run without either being
// throttled into failure or forcing the shipped default to be weakened -- which
// is the standing temptation this exists to remove.
func TestAZeroLimitDisablesTheControl(t *testing.T) {
	var logs bytes.Buffer
	app, served := newQuotaApp(newFakeQuotaStore(), 0, &logs)

	for i := 0; i < 50; i++ {
		fire(t, app).Body.Close()
	}
	if *served != 50 {
		t.Fatalf("a zero limit should disable the quota; served %d of 50", *served)
	}
}

// Fails CLOSED, unlike the speaking quota. An AI endpoint with no working
// budget check is exactly what this exists to prevent, and a cache outage is
// not a reason to hand out unlimited billed model calls.
func TestAnUnavailableStoreRefusesTheRequest(t *testing.T) {
	store := newFakeQuotaStore()
	store.fail = true
	var logs bytes.Buffer
	app, served := newQuotaApp(store, 10, &logs)

	resp := fire(t, app)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 when the quota store is down, got %d", resp.StatusCode)
	}
	if *served != 0 {
		t.Fatal("a request was served while the quota could not be checked")
	}
}

// The other fail-closed path, and it needs its own test: an erroring store and
// a missing store are different branches, and a mutation that opened the second
// one slipped past the test above.
func TestAMissingStoreRefusesTheRequest(t *testing.T) {
	var logs bytes.Buffer
	app, served := newQuotaApp(nil, 10, &logs)

	resp := fire(t, app)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 with no quota store configured, got %d", resp.StatusCode)
	}
	if *served != 0 {
		t.Fatal("a request was served with no quota store at all")
	}
}

func TestAnUnauthenticatedRequestIsRefused(t *testing.T) {
	var logs bytes.Buffer
	served := 0
	app := fiber.New()
	app.Post("/api/chat",
		AIRateLimiter(newFakeQuotaStore(), "chat", 10, time.Hour, zerolog.New(&logs)),
		func(c *fiber.Ctx) error { served++; return c.SendStatus(fiber.StatusOK) },
	)

	resp := fire(t, app)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("a quota keyed by user cannot run without a user; got %d", resp.StatusCode)
	}
	if served != 0 {
		t.Fatal("an unauthenticated request reached the handler")
	}
}

func TestExceedingTheQuotaWritesASecurityEvent(t *testing.T) {
	var logs bytes.Buffer
	app, _ := newQuotaApp(newFakeQuotaStore(), 1, &logs)

	fire(t, app).Body.Close()
	logs.Reset()
	fire(t, app).Body.Close()

	logged := logs.String()
	for _, field := range []string{
		`"event_type":"ai_quota_exceeded"`,
		`"severity":"MEDIUM"`,
		`"user_id":"user-123"`,
		`"correlation_id":"corr-1"`,
		`"action_taken":"rejected"`,
	} {
		if !bytes.Contains([]byte(logged), []byte(field)) {
			t.Errorf("security event missing %s: %s", field, logged)
		}
	}
}

func TestQuotasForDifferentEndpointsDoNotShareABudget(t *testing.T) {
	store := newFakeQuotaStore()
	var logs bytes.Buffer
	logger := zerolog.New(&logs)

	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(ContextKeyUserID, "user-123")
		return c.Next()
	})
	app.Post("/chat", AIRateLimiter(store, "chat", 1, time.Hour, logger),
		func(c *fiber.Ctx) error { return c.SendStatus(fiber.StatusOK) })
	app.Post("/essay", AIRateLimiter(store, "essay_evaluation", 1, time.Hour, logger),
		func(c *fiber.Ctx) error { return c.SendStatus(fiber.StatusOK) })

	for _, path := range []string{"/chat", "/essay"} {
		resp, err := app.Test(httptest.NewRequest(http.MethodPost, path, nil))
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("%s was refused on its first request (%d) -- the budgets are shared", path, resp.StatusCode)
		}
	}
}
