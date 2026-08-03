package middleware

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
)

// AIRateLimiter caps how often one user may invoke a specific AI endpoint
// (GOA-034, OWASP LLM04).
//
// The existing RateLimiter caps every /api route at 60 requests per minute,
// which treats /api/ping and a frontier-model call as the same thing. Sixty
// chat messages a minute from one user is sixty billed model calls a minute,
// and nothing about that is "hacked" -- the attacker simply spends your budget
// until real users get nothing. That is the most realistic attack on GOA,
// because it needs no skill at all.
//
// This runs *alongside* the per-minute limiter rather than replacing it. The
// two answer different questions: the minute window stops a burst, the hour
// window stops a slow drain that stays under it.
//
// Fixed window, like the existing limiter, and the boundary flaw is worse here:
// a user can spend a full hourly allowance at 10:59 and another at 11:00. A
// sliding window would fix it at the cost of more Redis operations per request.
// Accepted deliberately -- the failure costs at most one extra allowance, and
// the daily budget alarm in GOA-046 is the backstop for sustained abuse.
func AIRateLimiter(
	redisClient RateLimitStore,
	name string,
	limit int,
	window time.Duration,
	logger zerolog.Logger,
	metricCollectors ...*observability.Metrics,
) fiber.Handler {
	metrics := firstMetrics(metricCollectors)

	return func(c *fiber.Ctx) error {
		// A limit of zero disables the control. That is how the E2E suite and
		// the GOA-036 load test run without either weakening the shipped
		// defaults or being throttled into failure -- the alternative is a
		// standing temptation to lower a real limit to make a test pass.
		if limit <= 0 {
			return c.Next()
		}

		userID, _ := c.Locals(ContextKeyUserID).(string)
		if userID == "" {
			return fiber.NewError(fiber.StatusUnauthorized, "authenticated user not found")
		}

		if redisClient == nil {
			// Fail closed. An AI endpoint with no working budget check is
			// precisely the thing this exists to prevent, and Redis being down
			// is not a reason to hand out unlimited model calls.
			return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
		}

		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()

		bucket := time.Now().UTC().Truncate(window).Unix()
		key := fmt.Sprintf("gateway:ai_rate_limit:%s:%s:%d", name, userID, bucket)

		count, err := redisClient.Incr(ctx, key).Result()
		if err != nil {
			return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
		}
		if count == 1 {
			if err := redisClient.Expire(ctx, key, window).Err(); err != nil {
				return fiber.NewError(fiber.StatusServiceUnavailable, "rate limiter unavailable")
			}
		}

		if count > int64(limit) {
			ttl, err := redisClient.TTL(ctx, key).Result()
			if err != nil || ttl <= 0 {
				ttl = window
			}
			retryAfter := int((ttl + time.Second - 1) / time.Second)
			if retryAfter < 1 {
				retryAfter = 1
			}

			c.Set(fiber.HeaderRetryAfter, strconv.Itoa(retryAfter))
			metrics.RecordRateLimitHit(userID)
			metrics.RecordInputRejected("ai_quota")
			LogSecurityEvent(c, logger, SecurityEvent{
				EventType: "ai_quota_exceeded",
				// MEDIUM, not LOW: unlike an oversized message, repeatedly
				// hitting this is either abuse or a broken client, and both
				// cost money.
				Severity:    SeverityMedium,
				InputHash:   HashInput(name + ":" + userID),
				ActionTaken: "rejected",
				Extra: map[string]any{
					"quota":          name,
					"limit":          limit,
					"window_seconds": int(window.Seconds()),
					"count":          count,
				},
			})

			return fiber.NewError(
				fiber.StatusTooManyRequests,
				fmt.Sprintf("you have used your %s allowance; try again in %d seconds", name, retryAfter),
			)
		}

		return c.Next()
	}
}
