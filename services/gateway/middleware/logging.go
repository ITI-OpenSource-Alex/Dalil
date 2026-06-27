package middleware

import (
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
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

		route := c.Route().Path
		if route == "" {
			route = c.Path()
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
		metrics.RecordRequest(route, c.Method(), status, latency)

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

		route := c.Route().Path
		if route == "" {
			route = c.Path()
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
