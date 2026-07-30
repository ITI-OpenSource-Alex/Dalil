package middleware

import "github.com/gofiber/fiber/v2"

// AdminKey protects service-to-service administrative routes independently of
// user JWT authentication.
func AdminKey(expected string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		// TODO(GOA-027): Authenticate X-Admin-Key without allowing an unset
		// configured secret to become an open route. Reject empty/mismatched
		// values with the same 401 response, compare non-empty byte slices with
		// crypto/subtle.ConstantTimeCompare, and call c.Next only after a match.
		return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
			"error": "unauthorized",
		})
	}
}
