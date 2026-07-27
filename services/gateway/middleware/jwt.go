package middleware

import (
	"strings"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

// UserRevokedBeforeKey is the Redis key holding the unix second at or before
// which every access token for a user must be treated as revoked. Written by
// logout-all, read on every authenticated request.
func UserRevokedBeforeKey(userID string) string {
	return "user_revoked_before:" + userID
}

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

		// Per-user revocation epoch. The jti blacklist above can only cover tokens
		// whose jti is known, which for logout-all is just the calling session --
		// every other device's access token stayed valid for up to its full hour
		// after the user asked to be logged out everywhere (BUG-027). Comparing
		// iat against a single per-user timestamp revokes them all in O(1),
		// without the gateway needing to enumerate sessions.
		//
		// The comparison is <=, not <, so a token minted in the same second as the
		// revoke is also rejected. iat has one-second granularity, so the
		// alternative would leave a one-second window open on a security control.
		// The cost is that logging back in within the same second yields a token
		// that 401s once; the next login succeeds.
		if claims.Subject != "" && claims.IssuedAt != nil {
			if revokedAt, rerr := rdb.Get(c.Context(), UserRevokedBeforeKey(claims.Subject)).Int64(); rerr == nil {
				if claims.IssuedAt.Time.Unix() <= revokedAt {
					if metrics != nil {
						metrics.RecordAuthFailure()
					}
					return fiber.NewError(fiber.StatusUnauthorized, "token has been invalidated")
				}
			}
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
