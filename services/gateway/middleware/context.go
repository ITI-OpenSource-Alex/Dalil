package middleware

import (
	"strings"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/utils"
)

const (
	ContextKeyRequestID        = "request_id"
	ContextKeyUserID           = "user_id"
	ContextKeyRoute            = "route"
	ContextKeyUpstream         = "upstream_service"
	ContextKeySubscriptionTier = "subscription_tier"
	HeaderCorrelationID        = "X-Correlation-ID"
	HeaderSubscriptionTier     = "X-Subscription-Tier"
	HeaderForwardedFor         = "X-Forwarded-For"
	UpstreamServiceUnknown     = "gateway"
	AnonymousUserIdentifier    = "anonymous"
)

// ForwardedForChain preserves an inbound proxy chain and appends the immediate
// peer seen by the Gateway. Fiber/fasthttp header and address strings are
// buffer-backed, so every retained component is copied before concatenation.
func ForwardedForChain(c *fiber.Ctx) string {
	if c == nil {
		return ""
	}

	inbound := strings.TrimSpace(utils.CopyString(c.Get(HeaderForwardedFor)))
	peer := strings.TrimSpace(utils.CopyString(c.IP()))
	switch {
	case inbound == "":
		return peer
	case peer == "":
		return inbound
	default:
		return inbound + ", " + peer
	}
}
