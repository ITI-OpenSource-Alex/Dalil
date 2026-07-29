package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

func TestSubscriptionTierChangeIsObservedAfterRedisTTL(t *testing.T) {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://127.0.0.1:6379/0"
	}
	options, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("parse Redis URL: %v", err)
	}
	redisClient := redis.NewClient(options)
	t.Cleanup(func() { _ = redisClient.Close() })
	if err := redisClient.Ping(t.Context()).Err(); err != nil {
		t.Skipf("Redis integration dependency unavailable: %v", err)
	}

	userID := uuid.NewString()
	key := SubscriptionCacheKey(userID)
	t.Cleanup(func() { _ = redisClient.Del(t.Context(), key).Err() })

	var tier atomic.Value
	tier.Store("paid")
	var calls atomic.Int32
	userService := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/users/"+userID+"/subscription" {
			http.Error(w, "unexpected path", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{
			"subscriptionTier": tier.Load().(string),
		})
	}))
	t.Cleanup(userService.Close)

	subscriptions := NewSubscriptionMiddleware(
		redisClient,
		http.DefaultClient,
		userService.URL,
		"test-internal-key",
		"/upgrade",
		100*time.Millisecond,
		zerolog.Nop(),
	)
	app := subscriptionIntegrationApp(subscriptions, userID)

	if status := integrationRequestStatus(t, app); status != http.StatusNoContent {
		t.Fatalf("expected paid request to pass, got %d", status)
	}
	tier.Store("free")
	if status := integrationRequestStatus(t, app); status != http.StatusNoContent {
		t.Fatalf("expected cached paid tier before TTL, got %d", status)
	}
	if got := calls.Load(); got != 1 {
		t.Fatalf("expected one User service call before TTL, got %d", got)
	}

	time.Sleep(150 * time.Millisecond)
	if status := integrationRequestStatus(t, app); status != http.StatusForbidden {
		t.Fatalf("expected refreshed free tier after TTL, got %d", status)
	}
	if got := calls.Load(); got != 2 {
		t.Fatalf("expected second User service call after TTL, got %d", got)
	}
}

func subscriptionIntegrationApp(
	subscriptions *SubscriptionMiddleware,
	userID string,
) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(ContextKeyUserID, userID)
		return c.Next()
	})
	app.Use(subscriptions.ResolveSubscription)
	app.Get("/paid", subscriptions.RequirePaid, func(c *fiber.Ctx) error {
		return c.SendStatus(fiber.StatusNoContent)
	})
	return app
}

func integrationRequestStatus(t *testing.T, app *fiber.App) int {
	t.Helper()
	resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/paid", nil), -1)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	return resp.StatusCode
}
