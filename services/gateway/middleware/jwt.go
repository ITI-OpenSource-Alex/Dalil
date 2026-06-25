package middleware

import (
	"strings"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
)

func JWT(secret string, metricCollectors ...*observability.Metrics) fiber.Handler {
	tokenService := gatewayauth.NewTokenService(secret, time.Hour, 24*time.Hour)
	metrics := firstMetrics(metricCollectors)

	return func(c *fiber.Ctx) error {
		authHeader := c.Get(fiber.HeaderAuthorization)
		if authHeader == "" {
			metrics.RecordAuthFailure()
			return fiber.NewError(fiber.StatusUnauthorized, "missing authorization header")
		}

		parts := strings.Fields(authHeader)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") || parts[1] == "" {
			metrics.RecordAuthFailure()
			return fiber.NewError(fiber.StatusUnauthorized, "malformed authorization header")
		}

		claims, err := tokenService.ParseAccessToken(parts[1])
		if err != nil {
			metrics.RecordAuthFailure()
			return fiber.NewError(fiber.StatusUnauthorized, "invalid access token")
		}

		c.Locals(ContextKeyUserID, claims.Subject)
		return c.Next()
	}
}

func firstMetrics(metricCollectors []*observability.Metrics) *observability.Metrics {
	if len(metricCollectors) == 0 {
		return nil
	}

	return metricCollectors[0]
}
