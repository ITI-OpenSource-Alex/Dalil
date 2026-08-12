package middleware

import (
	"crypto/subtle"

	"github.com/gofiber/fiber/v2"
)

// InternalKey protects narrow service/operator endpoints with the shared
// service-to-service secret. It fails closed when the secret is not configured.
func InternalKey(expected string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		provided := c.Get("X-Internal-Api-Key")
		if expected == "" || provided == "" ||
			subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) != 1 {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{"error": "unauthorized"})
		}
		return c.Next()
	}
}
