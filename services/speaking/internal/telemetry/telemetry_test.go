package telemetry

import (
	"context"
	"encoding/base64"
	"os"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestRecordLLMCostAtUsesDailyServiceAndModelKeysWithTTL(t *testing.T) {
	server := miniredis.RunT(t)
	redisClient = redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() {
		_ = redisClient.Close()
	})

	recordedAt := time.Date(2026, 7, 30, 23, 59, 0, 0, time.UTC)
	recordLLMCostAt("user-1", "gpt-5.5", 100, 20, recordedAt)

	serviceKey := "llm:tokens:2026-07-30:user:user-1:speaking"
	modelKey := serviceKey + ":model:" +
		base64.RawURLEncoding.EncodeToString([]byte("gpt-5.5"))
	if got := server.HGet(serviceKey, "input"); got != "100" {
		t.Fatalf("expected service input tokens 100, got %q", got)
	}
	if got := server.HGet(modelKey, "output"); got != "20" {
		t.Fatalf("expected model output tokens 20, got %q", got)
	}
	if ttl := server.TTL(serviceKey); ttl != retentionSeconds*time.Second {
		t.Fatalf("expected %s TTL, got %s", retentionSeconds*time.Second, ttl)
	}

	recordLLMCostAt("user-1", "gpt-5.5", 10, 2, recordedAt.Add(time.Minute))
	if ttl := server.TTL(serviceKey); ttl != retentionSeconds*time.Second {
		t.Fatalf("expected NX expiry to preserve TTL, got %s", ttl)
	}
	if got, err := redisClient.HGet(
		context.Background(),
		"llm:tokens:2026-07-31:global",
		"input",
	).Int64(); err != nil || got != 10 {
		t.Fatalf("expected next UTC day global input 10, got %d (%v)", got, err)
	}
}

func TestRecordLLMCostIntegration(t *testing.T) {
	redisURL := os.Getenv("TEST_REDIS_GATEWAY_URL")
	if redisURL == "" {
		t.Skip("TEST_REDIS_GATEWAY_URL is not configured")
	}
	options, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatal(err)
	}
	redisClient = redis.NewClient(options)
	t.Cleanup(func() {
		_ = redisClient.Close()
	})

	recordLLMCostAt(
		"goa027-cost-e2e",
		"claude-opus-5",
		800,
		100,
		time.Now().UTC(),
	)
}
