package middleware

import (
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/utils"
	"github.com/rs/zerolog"
)

func RequestLogger(logger zerolog.Logger, metrics *observability.Metrics) fiber.Handler {
	return func(c *fiber.Ctx) error {
		start := time.Now()
		err := c.Next()
		if err != nil {
			if fiberError, ok := err.(*fiber.Error); ok {
				c.Status(fiberError.Code)
			} else {
				c.Status(fiber.StatusInternalServerError)
			}
		}

		// c.Route().Path is a registered route pattern -- an ordinary Go string
		// that outlives the request. c.Path() is not: like c.Method(), it is a
		// zero-copy view over fasthttp's reused request buffer and must be copied
		// before anything retains it (BUG-031).
		route := c.Route().Path
		if route == "" {
			route = utils.CopyString(c.Path())
		}

		status := c.Response().StatusCode()
		latency := time.Since(start)
		requestID, _ := c.Locals(ContextKeyRequestID).(string)
		userID, _ := c.Locals(ContextKeyUserID).(string)
		upstreamService, _ := c.Locals(ContextKeyUpstream).(string)

		if userID == "" {
			userID = AnonymousUserIdentifier
		}
		if upstreamService == "" {
			upstreamService = UpstreamServiceUnknown
		}

		c.Locals(ContextKeyRoute, route)
		// Prometheus keeps label values in its own map for the process lifetime,
		// so handing it fasthttp's buffer-backed string corrupted the series after
		// the buffer was reused: a POST to /auth/login surfaced as method "GETT",
		// and the mutated labels then collided with the originals. The whole
		// /metrics endpoint 500'd as a result -- "was collected before with the
		// same name and label values" -- so Prometheus could not scrape the
		// gateway at all (BUG-031).
		metrics.RecordRequest(route, utils.CopyString(c.Method()), status, latency)

		logger.Info().
			Str("request_id", requestID).
			Str("user_id", userID).
			Str("route", route).
			Int("status", status).
			Int64("latency_ms", latency.Milliseconds()).
			Str("upstream_service", upstreamService).
			Msg("request handled")

		return err
	}
}

func ErrorHandler(logger zerolog.Logger) fiber.ErrorHandler {
	return func(c *fiber.Ctx, err error) error {
		status := fiber.StatusInternalServerError
		message := "internal server error"
		if fiberError, ok := err.(*fiber.Error); ok {
			status = fiberError.Code
			message = fiberError.Message
		}

		// c.Route().Path is a registered route pattern -- an ordinary Go string
		// that outlives the request. c.Path() is not: like c.Method(), it is a
		// zero-copy view over fasthttp's reused request buffer and must be copied
		// before anything retains it (BUG-031).
		route := c.Route().Path
		if route == "" {
			route = utils.CopyString(c.Path())
		}

		requestID, _ := c.Locals(ContextKeyRequestID).(string)
		userID, _ := c.Locals(ContextKeyUserID).(string)
		upstreamService, _ := c.Locals(ContextKeyUpstream).(string)

		if userID == "" {
			userID = AnonymousUserIdentifier
		}
		if upstreamService == "" {
			upstreamService = UpstreamServiceUnknown
		}

		event := logger.Error()
		if status < fiber.StatusInternalServerError {
			event = logger.Warn()
		}

		event.
			Str("request_id", requestID).
			Str("user_id", userID).
			Str("route", route).
			Int("status", status).
			Str("upstream_service", upstreamService).
			Str("error", message).
			Msg("request error")

		return c.Status(status).JSON(fiber.Map{"error": message})
	}
}
