package middleware

import (
	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
)

func RequestID() fiber.Handler {
	return func(c *fiber.Ctx) error {
		requestID := c.Get(HeaderCorrelationID)
		if requestID == "" {
			requestID = uuid.NewString()
		}

		c.Locals(ContextKeyRequestID, requestID)
		c.Set(HeaderCorrelationID, requestID)

		return c.Next()
	}
}
