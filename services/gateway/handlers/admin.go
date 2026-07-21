package handlers

import (
	"context"
	"strconv"
	"strings"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

func AdminCosts(redisClient *redis.Client, budget float64, costPromptPer1M float64, costCompletionPer1M float64) fiber.Handler {
	return func(c *fiber.Ctx) error {
		ctx := context.Background()

		// Get global input/output tokens
		inputStr, _ := redisClient.HGet(ctx, "llm:tokens:global", "input").Result()
		outputStr, _ := redisClient.HGet(ctx, "llm:tokens:global", "output").Result()

		inputTokens, _ := strconv.ParseFloat(inputStr, 64)
		outputTokens, _ := strconv.ParseFloat(outputStr, 64)

		totalSpend := (inputTokens * costPromptPer1M / 1000000) + (outputTokens * costCompletionPer1M / 1000000)
		remainingQuota := budget - totalSpend

		// Get all user keys: llm:tokens:user:*
		var cursor uint64
		var keys []string
		userSpends := make(map[string]float64)

		for {
			var scanKeys []string
			var err error
			scanKeys, cursor, err = redisClient.Scan(ctx, cursor, "llm:tokens:user:*", 100).Result()
			if err != nil {
				return c.Status(500).JSON(fiber.Map{"error": "Failed to scan redis keys"})
			}
			keys = append(keys, scanKeys...)
			if cursor == 0 {
				break
			}
		}

		for _, key := range keys {
			uInputStr, _ := redisClient.HGet(ctx, key, "input").Result()
			uOutputStr, _ := redisClient.HGet(ctx, key, "output").Result()
			uInputTokens, _ := strconv.ParseFloat(uInputStr, 64)
			uOutputTokens, _ := strconv.ParseFloat(uOutputStr, 64)

			spend := (uInputTokens * costPromptPer1M / 1000000) + (uOutputTokens * costCompletionPer1M / 1000000)
			userID := strings.TrimPrefix(key, "llm:tokens:user:")
			userSpends[userID] = spend
		}

		return c.JSON(fiber.Map{
			"total_spend":     totalSpend,
			"remaining_quota": remainingQuota,
			"budget":          budget,
			"user_spends":     userSpends,
		})
	}
}
