package handlers

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

type modelPrice struct {
	PromptPer1M     float64 `json:"prompt_per_1m"`
	CompletionPer1M float64 `json:"completion_per_1m"`
}

type costBreakdown struct {
	RAGTokens      int64 `json:"rag_tokens"`
	WritingTokens  int64 `json:"writing_tokens"`
	SpeakingTokens int64 `json:"speaking_tokens"`
}

type userCost struct {
	UserID       string        `json:"userId"`
	TotalCostUSD float64       `json:"total_cost_usd"`
	Breakdown    costBreakdown `json:"breakdown"`
}

type adminCostsResponse struct {
	Date           string     `json:"date"`
	Users          []userCost `json:"users"`
	TotalSpend     float64    `json:"total_spend"`
	RemainingQuota float64    `json:"remaining_quota"`
	Budget         float64    `json:"budget"`
}

func AdminCosts(
	redisClient *redis.Client,
	budget float64,
	pricingJSON string,
	fallbackPromptPer1M float64,
	fallbackCompletionPer1M float64,
) fiber.Handler {
	prices := make(map[string]modelPrice)
	pricingErr := json.Unmarshal([]byte(pricingJSON), &prices)

	return func(c *fiber.Ctx) error {
		if pricingErr != nil || len(prices) == 0 {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "invalid LLM pricing configuration",
			})
		}

		date := time.Now().UTC().Format(time.DateOnly)
		prefix := "llm:tokens:" + date + ":user:"
		keys, err := scanKeys(c.UserContext(), redisClient, prefix+"*")
		if err != nil {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to scan cost data",
			})
		}

		users := make(map[string]*userCost)
		for _, key := range keys {
			parsed, ok := parseUserCostKey(key, prefix)
			if !ok {
				continue
			}
			values, err := redisClient.HGetAll(c.UserContext(), key).Result()
			if err != nil {
				return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
					"error": "failed to read cost data",
				})
			}
			inputTokens := parseTokenCount(values["input"])
			outputTokens := parseTokenCount(values["output"])
			entry := users[parsed.userID]
			if entry == nil {
				entry = &userCost{UserID: parsed.userID}
				users[parsed.userID] = entry
			}

			if parsed.model == "" {
				totalTokens := inputTokens + outputTokens
				switch parsed.service {
				case "rag":
					entry.Breakdown.RAGTokens += totalTokens
				case "writing":
					entry.Breakdown.WritingTokens += totalTokens
				case "speaking":
					entry.Breakdown.SpeakingTokens += totalTokens
				}
				continue
			}

			price, found := prices[parsed.model]
			if !found {
				price = modelPrice{
					PromptPer1M:     fallbackPromptPer1M,
					CompletionPer1M: fallbackCompletionPer1M,
				}
			}
			entry.TotalCostUSD +=
				(float64(inputTokens)*price.PromptPer1M +
					float64(outputTokens)*price.CompletionPer1M) / 1_000_000
		}

		responseUsers := make([]userCost, 0, len(users))
		totalSpend := 0.0
		for _, entry := range users {
			entry.TotalCostUSD = roundUSD(entry.TotalCostUSD)
			totalSpend += entry.TotalCostUSD
			responseUsers = append(responseUsers, *entry)
		}
		sort.Slice(responseUsers, func(i, j int) bool {
			return responseUsers[i].UserID < responseUsers[j].UserID
		})
		totalSpend = roundUSD(totalSpend)

		return c.JSON(adminCostsResponse{
			Date:           date,
			Users:          responseUsers,
			TotalSpend:     totalSpend,
			RemainingQuota: roundUSD(budget - totalSpend),
			Budget:         budget,
		})
	}
}

type parsedCostKey struct {
	userID  string
	service string
	model   string
}

func parseUserCostKey(key, prefix string) (parsedCostKey, bool) {
	if !strings.HasPrefix(key, prefix) {
		return parsedCostKey{}, false
	}
	remainder := strings.TrimPrefix(key, prefix)
	model := ""
	if marker := strings.LastIndex(remainder, ":model:"); marker >= 0 {
		encodedModel := remainder[marker+len(":model:"):]
		decodedModel, err := base64.RawURLEncoding.DecodeString(encodedModel)
		if err != nil || len(decodedModel) == 0 {
			return parsedCostKey{}, false
		}
		model = string(decodedModel)
		remainder = remainder[:marker]
	}
	serviceSeparator := strings.LastIndex(remainder, ":")
	if serviceSeparator <= 0 || serviceSeparator == len(remainder)-1 {
		return parsedCostKey{}, false
	}
	return parsedCostKey{
		userID:  remainder[:serviceSeparator],
		service: remainder[serviceSeparator+1:],
		model:   model,
	}, true
}

func scanKeys(
	ctx context.Context,
	redisClient *redis.Client,
	pattern string,
) ([]string, error) {
	var (
		cursor uint64
		keys   []string
	)
	for {
		page, nextCursor, err := redisClient.Scan(ctx, cursor, pattern, 100).Result()
		if err != nil {
			return nil, err
		}
		keys = append(keys, page...)
		cursor = nextCursor
		if cursor == 0 {
			return keys, nil
		}
	}
}

func parseTokenCount(value string) int64 {
	count, _ := strconv.ParseInt(value, 10, 64)
	return count
}

func roundUSD(value float64) float64 {
	return math.Round(value*100_000_000) / 100_000_000
}
