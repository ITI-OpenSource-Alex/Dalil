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
)

const examSessionOwnerKeyPrefix = "exam_session_owner:v1:"

// ExamOwnerStore is the slice of *redis.Client the ownership cache needs.
// Declared as an interface for the same reason RateLimitStore is: it lets a test
// drive the middleware without a Redis instance, and *redis.Client satisfies it
// directly so no adapter type is required.
type ExamOwnerStore interface {
	Get(ctx context.Context, key string) *redis.StringCmd
	Set(ctx context.Context, key string, value any, expiration time.Duration) *redis.StatusCmd
}

// ExamSessionOwnership rejects requests that name an exam session belonging to
// somebody else.
//
// Session routes take the session id from the URL, so without this check any
// authenticated candidate could submit or read another candidate's exam simply
// by pasting their session id -- the Exam service's session endpoints do not
// verify the caller, they only require the internal API key that the Gateway
// always sends.
type ExamSessionOwnership struct {
	store          ExamOwnerStore
	httpClient     *http.Client
	examServiceURL string
	internalAPIKey string
	cacheTTL       time.Duration
	logger         zerolog.Logger
}

func NewExamSessionOwnership(
	store ExamOwnerStore,
	httpClient *http.Client,
	examServiceURL string,
	internalAPIKey string,
	cacheTTL time.Duration,
	logger zerolog.Logger,
) *ExamSessionOwnership {
	return &ExamSessionOwnership{
		store:          store,
		httpClient:     httpClient,
		examServiceURL: strings.TrimRight(examServiceURL, "/"),
		internalAPIKey: internalAPIKey,
		cacheTTL:       cacheTTL,
		logger:         logger,
	}
}

// ExamSessionOwnerCacheKey keys the cache by session rather than by
// (session, user) pair. A session's owner never changes, so one entry answers
// every caller -- including the impostor, whose 403 is then served without a
// second upstream call.
func ExamSessionOwnerCacheKey(sessionID string) string {
	return examSessionOwnerKeyPrefix + sessionID
}

// Validate reads the session id from the :sessionId route parameter.
func (m *ExamSessionOwnership) Validate(c *fiber.Ctx) error {
	return m.validate(c, c.Params("sessionId"))
}

// ValidateQuery reads the session id from a query parameter instead of the path,
// for routes such as the Speaking WebSocket upgrade that carry it that way.
func (m *ExamSessionOwnership) ValidateQuery(name string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		return m.validate(c, c.Query(name))
	}
}

func (m *ExamSessionOwnership) validate(c *fiber.Ctx, sessionID string) error {
	userID, ok := c.Locals(ContextKeyUserID).(string)
	if !ok || userID == "" {
		return fiber.NewError(fiber.StatusUnauthorized, "authenticated user id is missing")
	}
	if sessionID == "" {
		return fiber.NewError(fiber.StatusBadRequest, "exam session id is required")
	}

	owner, err := m.resolveOwner(c, sessionID)
	if err != nil {
		return err
	}
	if owner != userID {
		return fiber.NewError(fiber.StatusForbidden, "exam session belongs to another user")
	}
	return c.Next()
}

// resolveOwner answers from Redis when it can and from the Exam service when it
// cannot.
//
// A cache fault falls through to the authoritative lookup rather than failing
// closed, which is the opposite of the subscription middleware's choice and for
// a different reason: the paywall has no authority to consult other than the
// cache, whereas ownership does. Denying here during a Redis blip would lock
// every candidate out of their own in-progress exam while the Exam service was
// answering correctly the whole time. If that call also fails the request is
// still refused, so an outage never becomes an authorisation bypass.
func (m *ExamSessionOwnership) resolveOwner(c *fiber.Ctx, sessionID string) (string, error) {
	key := ExamSessionOwnerCacheKey(sessionID)
	if m.store != nil {
		owner, err := m.store.Get(c.UserContext(), key).Result()
		switch {
		case err == nil && owner != "":
			return owner, nil
		case err != nil && !errors.Is(err, redis.Nil):
			m.logger.Error().
				Err(err).
				Str("exam_session_id", sessionID).
				Msg("exam session owner cache unavailable; falling back to exam service")
		}
	}

	owner, err := m.fetchOwner(c, sessionID)
	if err != nil {
		return "", err
	}

	if m.store != nil {
		if err := m.store.Set(c.UserContext(), key, owner, m.cacheTTL).Err(); err != nil {
			// A cache write failure costs latency on the next request, nothing more.
			m.logger.Error().
				Err(err).
				Str("exam_session_id", sessionID).
				Msg("exam session owner cache write failed")
		}
	}
	return owner, nil
}

func (m *ExamSessionOwnership) fetchOwner(c *fiber.Ctx, sessionID string) (string, error) {
	// url.JoinPath escapes the id, so a path-traversal attempt in the parameter
	// cannot reach a different upstream route.
	endpoint, err := url.JoinPath(m.examServiceURL, "internal", "sessions", sessionID, "owner")
	if err != nil {
		return "", fiber.NewError(fiber.StatusBadRequest, "invalid exam session id")
	}

	req, err := http.NewRequestWithContext(c.UserContext(), http.MethodGet, endpoint, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("X-Internal-API-Key", m.internalAPIKey)
	if requestID, _ := c.Locals(ContextKeyRequestID).(string); requestID != "" {
		req.Header.Set(HeaderCorrelationID, requestID)
	}
	if chain := ForwardedForChain(c); chain != "" {
		req.Header.Set(HeaderForwardedFor, chain)
	}

	resp, err := m.httpClient.Do(req)
	if err != nil {
		m.logger.Error().
			Err(err).
			Str("exam_session_id", sessionID).
			Msg("exam session owner lookup failed")
		return "", fiber.NewError(fiber.StatusBadGateway, "failed to contact exam service")
	}
	defer resp.Body.Close()

	// A missing session is relayed as 404 rather than 403. The candidate is not
	// forbidden from a session that does not exist, and flattening the two would
	// make a mistyped id indistinguishable from someone else's exam.
	if resp.StatusCode == http.StatusNotFound {
		return "", fiber.NewError(fiber.StatusNotFound, "exam session not found")
	}
	if resp.StatusCode != http.StatusOK {
		m.logger.Error().
			Str("exam_session_id", sessionID).
			Str("upstream_status", resp.Status).
			Msg("exam session owner lookup returned an unexpected status")
		return "", fiber.NewError(fiber.StatusBadGateway, "failed to resolve exam session owner")
	}

	var payload struct {
		UserID string `json:"user_id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return "", fiber.NewError(fiber.StatusBadGateway, "malformed exam session owner response")
	}
	if payload.UserID == "" {
		return "", fiber.NewError(fiber.StatusBadGateway, "exam service returned an empty session owner")
	}
	return payload.UserID, nil
}
