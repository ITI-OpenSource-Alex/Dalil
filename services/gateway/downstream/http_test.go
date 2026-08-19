package downstream

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func TestNewRequestPreservesAndAppendsForwardedFor(t *testing.T) {
	var forwardedFor string
	app := fiber.New()
	app.Get("/proxy", func(c *fiber.Ctx) error {
		req, err := NewRequest(c, http.MethodGet, "http://upstream.test", nil)
		if err != nil {
			return err
		}
		forwardedFor = req.Header.Get(middleware.HeaderForwardedFor)
		return c.SendStatus(fiber.StatusNoContent)
	})

	req := httptest.NewRequest(http.MethodGet, "/proxy", nil)
	req.RemoteAddr = "192.0.2.44:43120"
	req.Header.Set(middleware.HeaderForwardedFor, "203.0.113.8, 198.51.100.2")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("proxy request: %v", err)
	}
	defer resp.Body.Close()

	// Fiber's in-memory app.Test transport reports its peer as 0.0.0.0.
	// A real listener contributes the actual TCP peer at the same position.
	expected := "203.0.113.8, 198.51.100.2, 0.0.0.0"
	if forwardedFor != expected {
		t.Fatalf("expected %q, got %q", expected, forwardedFor)
	}
}
