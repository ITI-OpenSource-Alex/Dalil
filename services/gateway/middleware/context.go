package middleware

const (
	ContextKeyRequestID      = "request_id"
	ContextKeyUserID         = "user_id"
	ContextKeyRoute          = "route"
	ContextKeyUpstream       = "upstream_service"
	HeaderCorrelationID      = "X-Correlation-ID"
	UpstreamServiceUnknown   = "gateway"
	AnonymousUserIdentifier  = "anonymous"
)
