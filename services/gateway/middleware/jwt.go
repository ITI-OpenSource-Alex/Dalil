package middleware

import (
	"strings"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

// JWT validates access to
// and cross-checks the token's jti with the Redis blacklist cache.
func JWT(secret string, rdb *redis.Client, metricCollectors ...*observability.Metrics) fiber.Handler {
	tokenService := gatewayauth.NewTokenService(secret, time.Hour, 24*time.Hour)
	metrics := firstMetrics(metricCollectors)
	return func(c *fiber.Ctx) error {
		var tokenString string
		
		authHeader := c.Get(fiber.HeaderAuthorization)
		if authHeader != "" {
			parts := strings.Fields(authHeader)
			if len(parts) == 2 && strings.EqualFold(parts[0], "Bearer") {
				tokenString = parts[1]
			}
		}
		
		if tokenString == "" {
			tokenString = c.Cookies("access_token")
		}
		if tokenString == "" {
			if metrics != nil {
				metrics.RecordAuthFailure()
			}
			return fiber.NewError(fiber.StatusUnauthorized, "missing or invalid authorization token")
		}
		
		claims, err := tokenService.ParseAccessToken(tokenString)
		if err != nil {
			if metrics != nil {
				metrics.RecordAuthFailure()
			}
			return fiber.NewError(fiber.StatusUnauthorized, "invalid access token")
		}
		
		blacklisted, err := rdb.Exists(c.Context(), "jti:"+claims.ID).Result()
		if err == nil && blacklisted > 0 {
			if metrics != nil {
				metrics.RecordAuthFailure()
			}
			return fiber.NewError(fiber.StatusUnauthorized, "token has been invalidated")
		}
		
		c.Locals(ContextKeyUserID, claims.Subject)
		c.Locals("jti", claims.ID)
		if claims.ExpiresAt != nil {
			c.Locals("tokenExp", claims.ExpiresAt.Time)
		}
		return c.Next()
	}
}
func firstMetrics(metricCollectors []*observability.Metrics) *observability.Metrics {
	if len(metricCollectors) == 0 {
		return nil
	}
	return metricCollectors[0]
}
