package telemetry

import (
	"context"
	"os"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog/log"
)

var redisClient *redis.Client

func init() {
	redisURL := os.Getenv("REDIS_GATEWAY_URL")
	if redisURL == "" {
		redisURL = "redis://redis-gateway:6379/0"
	}
	opts, err := redis.ParseURL(redisURL)
	if err == nil {
		redisClient = redis.NewClient(opts)
	} else {
		log.Error().Err(err).Msg("Failed to parse REDIS_GATEWAY_URL")
	}
}

func RecordLLMCost(userID string, model string, inputTokens int64, outputTokens int64) {
	if redisClient == nil {
		return
	}
	ctx := context.Background()

	if inputTokens > 0 {
		redisClient.HIncrBy(ctx, "llm:tokens:user:"+userID, "input", inputTokens)
		redisClient.HIncrBy(ctx, "llm:tokens:global", "input", inputTokens)
	}
	if outputTokens > 0 {
		redisClient.HIncrBy(ctx, "llm:tokens:user:"+userID, "output", outputTokens)
		redisClient.HIncrBy(ctx, "llm:tokens:global", "output", outputTokens)
	}
}
