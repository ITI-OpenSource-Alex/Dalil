package middleware

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
	"golang.org/x/sync/singleflight"
)

type SubscriptionTier string

const (
	SubscriptionTierFree SubscriptionTier = "free"
	SubscriptionTierPaid SubscriptionTier = "paid"

	subscriptionCacheKeyPrefix = "subtier:v1:"
)

type subscriptionCache interface {
	Get(ctx context.Context, key string) (string, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
}

type redisSubscriptionCache struct {
	client *redis.Client
}

func (c redisSubscriptionCache) Get(ctx context.Context, key string) (string, error) {
	return c.client.Get(ctx, key).Result()
}

func (c redisSubscriptionCache) Set(
	ctx context.Context,
	key string,
	value string,
	ttl time.Duration,
) error {
	return c.client.Set(ctx, key, value, ttl).Err()
}

type SubscriptionMiddleware struct {
	cache          subscriptionCache
	httpClient     *http.Client
	userServiceURL string
	internalAPIKey string
	upgradeURL     string
	cacheTTL       time.Duration
	logger         zerolog.Logger
	lookups        singleflight.Group
}

func NewSubscriptionMiddleware(
	redisClient *redis.Client,
	httpClient *http.Client,
	userServiceURL string,
	internalAPIKey string,
	upgradeURL string,
	cacheTTL time.Duration,
	logger zerolog.Logger,
) *SubscriptionMiddleware {
	return &SubscriptionMiddleware{
		cache:          redisSubscriptionCache{client: redisClient},
		httpClient:     httpClient,
		userServiceURL: strings.TrimRight(userServiceURL, "/"),
		internalAPIKey: internalAPIKey,
		upgradeURL:     upgradeURL,
		cacheTTL:       cacheTTL,
		logger:         logger,
	}
}

func SubscriptionCacheKey(userID string) string {
	return subscriptionCacheKeyPrefix + userID
}

// ResolveSubscription stores the authoritative tier in Fiber locals for later
// route policy and downstream-header forwarding.
//
// Redis failures deliberately fail closed: the current request is treated as
// free tier and the failure is logged. This keeps the paywall intact during a
// cache outage at the cost of temporarily blocking paid features.
func (m *SubscriptionMiddleware) ResolveSubscription(c *fiber.Ctx) error {
	userID, _ := c.Locals(ContextKeyUserID).(string)
	if userID == "" {
		return fiber.NewError(fiber.StatusUnauthorized, "authenticated user id is missing")
	}

	key := SubscriptionCacheKey(userID)
	tier, cacheErr := m.cachedTier(c.UserContext(), key)
	if cacheErr == nil {
		c.Locals(ContextKeySubscriptionTier, string(tier))
		return c.Next()
	}
	if !errors.Is(cacheErr, redis.Nil) {
		m.logger.Error().
			Err(cacheErr).
			Str("user_id", userID).
			Msg("subscription cache unavailable; failing closed")
		c.Locals(ContextKeySubscriptionTier, string(SubscriptionTierFree))
		return c.Next()
	}

	resolved, _, _ := m.lookups.Do(key, func() (any, error) {
		// A concurrent request may have filled the cache while this request
		// waited for the singleflight lock.
		if cached, err := m.cachedTier(c.UserContext(), key); err == nil {
			return cached, nil
		} else if !errors.Is(err, redis.Nil) {
			m.logger.Error().
				Err(err).
				Str("user_id", userID).
				Msg("subscription cache unavailable during lookup; failing closed")
			return SubscriptionTierFree, nil
		}

		tier, err := m.fetchTier(c.UserContext(), userID, c)
		if err != nil {
			m.logger.Error().
				Err(err).
				Str("user_id", userID).
				Msg("subscription lookup failed; failing closed")
			return SubscriptionTierFree, nil
		}

		if err := m.cache.Set(c.UserContext(), key, string(tier), m.cacheTTL); err != nil {
			m.logger.Error().
				Err(err).
				Str("user_id", userID).
				Msg("subscription cache write failed; failing closed")
			return SubscriptionTierFree, nil
		}
		return tier, nil
	})

	tier = resolved.(SubscriptionTier)
	c.Locals(ContextKeySubscriptionTier, string(tier))
	return c.Next()
}

func (m *SubscriptionMiddleware) RequirePaid(c *fiber.Ctx) error {
	tier, _ := c.Locals(ContextKeySubscriptionTier).(string)
	if tier == string(SubscriptionTierPaid) {
		return c.Next()
	}

	return c.Status(fiber.StatusForbidden).JSON(fiber.Map{
		"error":      "subscription_required",
		"upgradeUrl": m.upgradeURL,
	})
}

func (m *SubscriptionMiddleware) cachedTier(
	ctx context.Context,
	key string,
) (SubscriptionTier, error) {
	value, err := m.cache.Get(ctx, key)
	if err != nil {
		return "", err
	}

	tier := SubscriptionTier(value)
	if tier != SubscriptionTierFree && tier != SubscriptionTierPaid {
		m.logger.Warn().
			Str("cache_key", key).
			Str("cached_value", value).
			Msg("ignoring invalid cached subscription tier")
		return "", redis.Nil
	}
	return tier, nil
}

func (m *SubscriptionMiddleware) fetchTier(
	ctx context.Context,
	userID string,
	fiberCtx *fiber.Ctx,
) (SubscriptionTier, error) {
	endpoint, err := url.JoinPath(m.userServiceURL, "users", userID, "subscription")
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("X-Internal-API-Key", m.internalAPIKey)
	if requestID, _ := fiberCtx.Locals(ContextKeyRequestID).(string); requestID != "" {
		req.Header.Set(HeaderCorrelationID, requestID)
	}

	resp, err := m.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", errors.New("user service returned " + resp.Status)
	}

	var payload struct {
		SubscriptionTier SubscriptionTier `json:"subscriptionTier"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return "", err
	}
	if payload.SubscriptionTier != SubscriptionTierFree &&
		payload.SubscriptionTier != SubscriptionTierPaid {
		return "", errors.New("user service returned an invalid subscription tier")
	}
	return payload.SubscriptionTier, nil
}
