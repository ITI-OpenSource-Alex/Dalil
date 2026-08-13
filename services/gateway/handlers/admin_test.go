package handlers

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

const testPricing = `{
	"claude-opus-4-8":{"prompt_per_1m":2,"completion_per_1m":10},
	"gpt-5.5":{"prompt_per_1m":7,"completion_per_1m":14}
}`

func TestAdminCostsReturnsDailyPerServiceBreakdownAndModelPricing(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() {
		_ = client.Close()
	})
	date := time.Now().UTC().Format(time.DateOnly)

	writeCostFixture(t, server, date, "user-a", "rag", "claude-opus-4-8", 1000, 200)
	writeCostFixture(t, server, date, "user-a", "writing", "gpt-5.5", 7000, 600)
	writeCostFixture(t, server, date, "user-b", "speaking", "gpt-5.5", 1000, 200)
	writeCostFixture(t, server, "2026-01-01", "old-user", "rag", "gpt-5.5", 999, 999)

	app := fiber.New()
	app.Get("/admin/costs", AdminCosts(client, 150, testPricing, 2, 10))
	response, err := app.Test(httptest.NewRequest("GET", "/admin/costs", nil))
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}

	var body adminCostsResponse
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Date != date {
		t.Fatalf("expected date %s, got %s", date, body.Date)
	}
	if len(body.Users) != 2 {
		t.Fatalf("expected only today's two users, got %+v", body.Users)
	}
	userA := body.Users[0]
	if userA.UserID != "user-a" {
		t.Fatalf("users were not deterministically sorted: %+v", body.Users)
	}
	if userA.Breakdown.RAGTokens != 1200 ||
		userA.Breakdown.WritingTokens != 7600 ||
		userA.Breakdown.SpeakingTokens != 0 {
		t.Fatalf("unexpected service breakdown: %+v", userA.Breakdown)
	}
	if userA.TotalCostUSD != 0.0614 {
		t.Fatalf("expected per-model cost 0.0614, got %.8f", userA.TotalCostUSD)
	}
	if body.Users[1].TotalCostUSD != 0.0098 {
		t.Fatalf("expected gpt-5.5 cost 0.0098, got %.8f", body.Users[1].TotalCostUSD)
	}
	if body.TotalSpend != 0.0712 || body.RemainingQuota != 149.9288 {
		t.Fatalf("unexpected quota totals: %+v", body)
	}
}

func TestAdminCostsRejectsInvalidPricingConfiguration(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() {
		_ = client.Close()
	})
	app := fiber.New()
	app.Get("/admin/costs", AdminCosts(client, 150, "{", 2, 10))

	response, err := app.Test(httptest.NewRequest("GET", "/admin/costs", nil))
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", response.StatusCode)
	}
}

func TestAdminCostsUsesConfiguredFallbackForUnknownModel(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() {
		_ = client.Close()
	})
	date := time.Now().UTC().Format(time.DateOnly)

	writeCostFixture(t, server, date, "fallback-user", "rag", "unrecognized-model-id", 2000, 300)

	app := fiber.New()
	app.Get("/admin/costs", AdminCosts(client, 150, testPricing, 6, 30))
	response, err := app.Test(httptest.NewRequest("GET", "/admin/costs", nil))
	if err != nil {
		t.Fatal(err)
	}

	var body adminCostsResponse
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if len(body.Users) != 1 {
		t.Fatalf("expected one fallback-priced user, got %+v", body.Users)
	}
	if body.Users[0].TotalCostUSD != 0.021 {
		t.Fatalf("expected $6/$30 fallback cost 0.021, got %.8f", body.Users[0].TotalCostUSD)
	}
}

func writeCostFixture(
	t *testing.T,
	server *miniredis.Miniredis,
	date string,
	userID string,
	service string,
	model string,
	input int,
	output int,
) {
	t.Helper()
	serviceKey := fmt.Sprintf(
		"llm:tokens:%s:user:%s:%s",
		date,
		userID,
		service,
	)
	modelKey := serviceKey + ":model:" +
		base64.RawURLEncoding.EncodeToString([]byte(model))
	for _, key := range []string{serviceKey, modelKey} {
		server.HSet(key, "input", fmt.Sprint(input))
		server.HSet(key, "output", fmt.Sprint(output))
	}
}
