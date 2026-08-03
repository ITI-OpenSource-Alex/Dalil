package middleware

import (
	"encoding/json"
	"fmt"
	"unicode/utf8"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
)

// ValidateJSONFieldLength rejects a request whose named JSON field is longer
// than maxChars.
//
// The JSON-body counterpart to ValidateEssayTextLength, which does the same job
// for multipart uploads. POST /api/chat had no limit at all, which left three
// problems open at once: an unbounded message is an unbounded token bill, a
// very long one is slow enough to be a denial-of-service lever, and a huge
// context pushes the system prompt far enough from the model's attention that
// its instructions are followed less reliably. One check closes all three.
//
// Characters, not bytes. len() on a Go string counts bytes, and Arabic is
// roughly three bytes per character -- a 2000-byte limit would cut an Egyptian
// student off at about 660 characters while an English speaker got 2000. That
// asymmetry would never show up in testing here and would be immediate in
// production.
func ValidateJSONFieldLength(
	field string,
	maxChars int,
	logger zerolog.Logger,
	metricCollectors ...*observability.Metrics,
) fiber.Handler {
	metrics := firstMetrics(metricCollectors)

	return func(c *fiber.Ctx) error {
		body := c.Body()
		if len(body) == 0 {
			return c.Next()
		}

		// Decoding into json.RawMessage means only the field we care about is
		// parsed as a value. The rest of the body stays untouched bytes, so
		// this middleware cannot fail on a shape it was never meant to police.
		var payload map[string]json.RawMessage
		if err := json.Unmarshal(body, &payload); err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "invalid JSON body")
		}

		raw, present := payload[field]
		if !present {
			// Whether the field is required belongs to the schema, not here.
			// A middleware with one job is a middleware you can reason about.
			return c.Next()
		}

		var value string
		if err := json.Unmarshal(raw, &value); err != nil {
			return fiber.NewError(
				fiber.StatusBadRequest,
				fmt.Sprintf("%s must be a string", field),
			)
		}

		length := utf8.RuneCountInString(value)
		if length <= maxChars {
			return c.Next()
		}

		metrics.RecordInputRejected("length")
		LogSecurityEvent(c, logger, SecurityEvent{
			EventType:   "input_length_exceeded",
			Severity:    SeverityLow,
			InputHash:   HashInput(value),
			ActionTaken: "rejected",
			Extra: map[string]any{
				"field":      field,
				"length":     length,
				"max_length": maxChars,
			},
		})

		return fiber.NewError(
			fiber.StatusBadRequest,
			fmt.Sprintf("%s exceeds maximum length of %d characters", field, maxChars),
		)
	}
}
