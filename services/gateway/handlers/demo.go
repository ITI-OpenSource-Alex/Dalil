package handlers

import (
	"context"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// DemoResetAIQuotas resets only the named user's hourly AI counters. The
// Gateway owns those Redis keys, so the demo operator must not delete them
// directly from Redis.
func DemoResetAIQuotas(client *redis.Client) fiber.Handler {
	return func(c *fiber.Ctx) error {
		userID := c.Params("userId")
		if _, err := uuid.Parse(userID); err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "invalid user id")
		}
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()

		pattern := fmt.Sprintf("gateway:ai_rate_limit:*:%s:*", userID)
		var keys []string
		var cursor uint64
		for {
			batch, next, err := client.Scan(ctx, cursor, pattern, 100).Result()
			if err != nil {
				return fiber.NewError(fiber.StatusServiceUnavailable, "quota store unavailable")
			}
			keys = append(keys, batch...)
			cursor = next
			if cursor == 0 {
				break
			}
		}
		if len(keys) > 0 {
			if err := client.Del(ctx, keys...).Err(); err != nil {
				return fiber.NewError(fiber.StatusServiceUnavailable, "quota store unavailable")
			}
		}
		return c.JSON(fiber.Map{"status": "reset", "deleted": len(keys)})
	}
}
