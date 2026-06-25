package handlers

import (
	"time"

	"github.com/gofiber/fiber/v2"
)

func Health(startTime time.Time, version string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"status":  "ok",
			"version": version,
			"uptime":  time.Since(startTime).String(),
		})
	}
}
