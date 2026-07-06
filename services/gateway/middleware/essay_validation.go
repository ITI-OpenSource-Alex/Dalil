package middleware

import (
	"github.com/gofiber/fiber/v2"
)

func ValidateEssayTextLength(maxLength int) fiber.Handler {
	return func(c *fiber.Ctx) error {
		form, err := c.MultipartForm()
		if err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "invalid multipart form data")
		}

		essayTexts := form.Value["essayText"]
		if len(essayTexts) == 0 {
			return fiber.NewError(fiber.StatusBadRequest, "essayText is required")
		}

		essayText := essayTexts[0]

		if len(essayText) > maxLength {
			return fiber.NewError(
				fiber.StatusBadRequest,
				"essayText exceeds maximum length of 5000 characters",
			)
		}

		return c.Next()
	}
}