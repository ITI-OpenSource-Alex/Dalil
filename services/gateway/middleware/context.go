package middleware

const (
	ContextKeyRequestID        = "request_id"
	ContextKeyUserID           = "user_id"
	ContextKeyRoute            = "route"
	ContextKeyUpstream         = "upstream_service"
	ContextKeySubscriptionTier = "subscription_tier"
	HeaderCorrelationID        = "X-Correlation-ID"
	HeaderSubscriptionTier     = "X-Subscription-Tier"
	UpstreamServiceUnknown     = "gateway"
	AnonymousUserIdentifier    = "anonymous"
)
