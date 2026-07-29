package handlers

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func TestChatForwardsSubscriptionTierAndAuthoritativeUserID(t *testing.T) {
	var receivedTier string
	var receivedUserID string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedTier = r.Header.Get(middleware.HeaderSubscriptionTier)
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			http.Error(w, "invalid body", http.StatusBadRequest)
			return
		}
		receivedUserID, _ = payload["userId"].(string)
		w.Header().Set(fiber.HeaderContentType, "text/event-stream")
		_, _ = io.WriteString(w, "event: token\ndata: {\"type\":\"token\",\"content\":\"ok\"}\n\n")
	}))
	t.Cleanup(upstream.Close)

	handler := NewStreamHandler(
		http.DefaultClient,
		upstream.URL,
		"http://writing.invalid",
		"test-internal-key",
	)
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "jwt-user")
		c.Locals(middleware.ContextKeySubscriptionTier, "paid")
		return c.Next()
	})
	app.Post("/chat", handler.Chat)

	req := httptest.NewRequest(
		http.MethodPost,
		"/chat",
		bytes.NewBufferString(`{"userId":"forged-user","message":"hello","sessionId":"s1"}`),
	)
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	resp, err := app.Test(req, -1)
	if err != nil {
		t.Fatalf("chat request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
	if receivedTier != "paid" {
		t.Fatalf("expected paid subscription header, got %q", receivedTier)
	}
	if receivedUserID != "jwt-user" {
		t.Fatalf("expected JWT user id, got %q", receivedUserID)
	}
}
