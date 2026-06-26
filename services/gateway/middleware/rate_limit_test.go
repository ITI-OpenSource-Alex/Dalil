package middleware

import (
	"context"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

func TestRateLimiterAllowsFirst60Requests(t *testing.T) {
	app := newRateLimitTestApp(newFakeRateLimitStore(), 60)

	for i := 0; i < 60; i++ {
		resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/api/ping", nil))
		if err != nil {
			t.Fatalf("request %d returned error: %v", i+1, err)
		}
		if resp.StatusCode != fiber.StatusOK {
			t.Fatalf("request %d expected status 200, got %d", i+1, resp.StatusCode)
		}
	}
}

func TestRateLimiterBlocks61stRequestAndSetsRetryAfter(t *testing.T) {
	app := newRateLimitTestApp(newFakeRateLimitStore(), 60)

	for i := 0; i < 60; i++ {
		resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/api/ping", nil))
		if err != nil {
			t.Fatalf("request %d returned error: %v", i+1, err)
		}
		if resp.StatusCode != fiber.StatusOK {
			t.Fatalf("request %d expected status 200, got %d", i+1, resp.StatusCode)
		}
	}

	resp, err := app.Test(httptest.NewRequest(fiber.MethodGet, "/api/ping", nil))
	if err != nil {
		t.Fatalf("blocked request returned error: %v", err)
	}
	if resp.StatusCode != fiber.StatusTooManyRequests {
		t.Fatalf("expected status 429, got %d", resp.StatusCode)
	}
	if retryAfter := resp.Header.Get(fiber.HeaderRetryAfter); retryAfter == "" {
		t.Fatal("expected Retry-After header to be set")
	}
}

func newRateLimitTestApp(store RateLimitStore, limit int) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(ContextKeyUserID, "user-1")
		return c.Next()
	})
	app.Use(RateLimiter(store, limit))
	app.Get("/api/ping", func(c *fiber.Ctx) error {
		return c.SendStatus(fiber.StatusOK)
	})

	return app
}

type fakeRateLimitStore struct {
	counts map[string]int64
	ttls   map[string]time.Duration
}

func newFakeRateLimitStore() *fakeRateLimitStore {
	return &fakeRateLimitStore{
		counts: make(map[string]int64),
		ttls:   make(map[string]time.Duration),
	}
}

func (s *fakeRateLimitStore) Incr(_ context.Context, key string) *redis.IntCmd {
	s.counts[key]++
	return redis.NewIntResult(s.counts[key], nil)
}

func (s *fakeRateLimitStore) Expire(_ context.Context, key string, expiration time.Duration) *redis.BoolCmd {
	s.ttls[key] = expiration
	return redis.NewBoolResult(true, nil)
}

func (s *fakeRateLimitStore) TTL(_ context.Context, key string) *redis.DurationCmd {
	ttl := s.ttls[key]
	if ttl == 0 {
		ttl = time.Minute
	}

	return redis.NewDurationResult(ttl, nil)
}
