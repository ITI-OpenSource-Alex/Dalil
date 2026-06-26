package middleware

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

type RateLimitStore interface {
	Incr(ctx context.Context, key string) *redis.IntCmd
	Expire(ctx context.Context, key string, expiration time.Duration) *redis.BoolCmd
	TTL(ctx context.Context, key string) *redis.DurationCmd
}

func RateLimiter(redisClient RateLimitStore, limit int, metricCollectors ...*observability.Metrics) fiber.Handler {
	metrics := firstMetrics(metricCollectors)
	if limit <= 0 {
		limit = 60
	}

	return func(c *fiber.Ctx) error {
		userID, _ := c.Locals(ContextKeyUserID).(string)
		if userID == "" {
			return fiber.NewError(fiber.StatusUnauthorized, "authenticated user not found")
		}

		if redisClient == nil {
			return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
		}

		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()

		window := time.Now().UTC().Truncate(time.Minute).Unix()
		key := fmt.Sprintf("gateway:rate_limit:%s:%d", userID, window)
		count, err := redisClient.Incr(ctx, key).Result()
		if err != nil {
			return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
		}

		if count == 1 {
			if err := redisClient.Expire(ctx, key, time.Minute).Err(); err != nil {
				return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
			}
		}

		if count > int64(limit) {
			ttl, err := redisClient.TTL(ctx, key).Result()
			if err != nil || ttl <= 0 {
				ttl = time.Minute
			}

			retryAfter := int((ttl + time.Second - 1) / time.Second)
			if retryAfter < 1 {
				retryAfter = 1
			}

			c.Set(fiber.HeaderRetryAfter, strconv.Itoa(retryAfter))
			metrics.RecordRateLimitHit(userID)
			return fiber.NewError(fiber.StatusTooManyRequests, "rate limit exceeded")
		}

		return c.Next()
	}
}
