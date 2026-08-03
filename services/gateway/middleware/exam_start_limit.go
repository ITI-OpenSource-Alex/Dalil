package middleware

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
)

// ExamStartRateLimiter caps how many exam sessions one candidate may open per
// hour. It reuses RateLimitStore rather than introducing a second store
// abstraction; only the window and the key differ from RateLimiter.
//
// This is a separate limiter, not a tighter setting on the generic one, because
// the two count different things. The generic limiter counts requests and resets
// every minute; this one counts *sessions created* and has to hold a candidate
// to three across a whole hour, which a minute window cannot express.
//
// The key is exam_start:{userId}:{hour} with the hour as a UTC calendar hour, so
// an operator reading Redis directly can tell which window a counter belongs to.
func ExamStartRateLimiter(
	store RateLimitStore,
	limit int,
	metricCollectors ...*observability.Metrics,
) fiber.Handler {
	metrics := firstMetrics(metricCollectors)
	if limit <= 0 {
		limit = 3
	}

	return func(c *fiber.Ctx) error {
		userID, _ := c.Locals(ContextKeyUserID).(string)
		if userID == "" {
			return fiber.NewError(fiber.StatusUnauthorized, "authenticated user not found")
		}

		if store == nil {
			return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
		}

		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()

		now := time.Now().UTC()
		key := fmt.Sprintf("exam_start:%s:%s", userID, now.Format("2006-01-02T15"))
		count, err := store.Incr(ctx, key).Result()
		if err != nil {
			return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
		}

		// Expire on the first increment only. Re-arming it on every request would
		// slide the window forward and let a steady trickle of starts never reset.
		if count == 1 {
			if err := store.Expire(ctx, key, time.Hour).Err(); err != nil {
				return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
			}
		}

		if count > int64(limit) {
			ttl, err := store.TTL(ctx, key).Result()
			if err != nil || ttl <= 0 {
				ttl = time.Hour
			}

			retryAfter := int((ttl + time.Second - 1) / time.Second)
			if retryAfter < 1 {
				retryAfter = 1
			}

			c.Set(fiber.HeaderRetryAfter, strconv.Itoa(retryAfter))
			metrics.RecordRateLimitHit(userID)
			return fiber.NewError(
				fiber.StatusTooManyRequests,
				"exam session start limit reached; try again later",
			)
		}

		return c.Next()
	}
}
