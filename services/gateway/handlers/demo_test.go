package handlers

import (
	"net/http/httptest"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestDemoResetAIQuotasDeletesOnlyNamedUser(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	userID := uuid.NewString()
	otherID := uuid.NewString()
	mr.Set("gateway:ai_rate_limit:opportunity_search:"+userID+":1", "21")
	mr.Set("gateway:ai_rate_limit:chat:"+userID+":1", "20")
	mr.Set("gateway:ai_rate_limit:chat:"+otherID+":1", "20")

	app := fiber.New()
	app.Post("/internal/demo/users/:userId/quotas/reset", DemoResetAIQuotas(client))
	response, err := app.Test(httptest.NewRequest(
		fiber.MethodPost, "/internal/demo/users/"+userID+"/quotas/reset", nil,
	))
	if err != nil || response.StatusCode != fiber.StatusOK {
		t.Fatalf("reset failed: status=%d err=%v", response.StatusCode, err)
	}
	if mr.Exists("gateway:ai_rate_limit:chat:"+userID+":1") ||
		mr.Exists("gateway:ai_rate_limit:opportunity_search:"+userID+":1") {
		t.Fatal("named user's quota keys remain")
	}
	if !mr.Exists("gateway:ai_rate_limit:chat:" + otherID + ":1") {
		t.Fatal("another user's quota was deleted")
	}
	_ = client.Close()
}
