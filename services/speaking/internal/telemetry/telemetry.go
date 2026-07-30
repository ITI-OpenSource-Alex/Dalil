package telemetry

import (
	"context"
	"encoding/base64"
	"os"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog/log"
)

var redisClient *redis.Client

const (
	serviceName      = "speaking"
	retentionSeconds = 35 * 24 * 60 * 60
)

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
	recordLLMCostAt(userID, model, inputTokens, outputTokens, time.Now().UTC())
}

func recordLLMCostAt(
	userID string,
	model string,
	inputTokens int64,
	outputTokens int64,
	recordedAt time.Time,
) {
	if redisClient == nil {
		return
	}
	if inputTokens <= 0 && outputTokens <= 0 {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	date := recordedAt.UTC().Format(time.DateOnly)
	encodedModel := base64.RawURLEncoding.EncodeToString([]byte(model))
	if encodedModel == "" {
		encodedModel = base64.RawURLEncoding.EncodeToString([]byte("unknown"))
	}
	serviceKey := "llm:tokens:" + date + ":user:" + userID + ":" + serviceName
	globalKey := "llm:tokens:" + date + ":global"
	keys := []string{
		serviceKey,
		globalKey,
		serviceKey + ":model:" + encodedModel,
		globalKey + ":model:" + encodedModel,
	}

	_, err := redisClient.Pipelined(ctx, func(pipe redis.Pipeliner) error {
		for _, key := range keys {
			if inputTokens > 0 {
				pipe.HIncrBy(ctx, key, "input", inputTokens)
			}
			if outputTokens > 0 {
				pipe.HIncrBy(ctx, key, "output", outputTokens)
			}
			pipe.ExpireNX(ctx, key, retentionSeconds*time.Second)
		}
		return nil
	})
	if err != nil {
		log.Error().Err(err).Msg("Failed to record LLM cost telemetry")
	}
}
