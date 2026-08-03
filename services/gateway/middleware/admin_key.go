package middleware

import (
	"crypto/subtle"

	"github.com/gofiber/fiber/v2"
)

// AdminKey protects service-to-service administrative routes independently of
// user JWT authentication.
func AdminKey(expected string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		provided := c.Get("X-Admin-Key")
		if expected == "" ||
			provided == "" ||
			subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) != 1 {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"error": "unauthorized",
			})
		}

		return c.Next()
	}
}
