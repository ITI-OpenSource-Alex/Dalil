package handlers

import (
	"bytes"
	"io"
	"net/http"
	"net/url"
	"path"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// SpeakingHandler proxies Speaking's session-history routes.
//
// GOA-132's acceptance criteria name only the WebSocket, but its own regression
// criterion ("a grep for direct :8082 in services/frontend returns nothing")
// cannot pass without these, and there is a real defect behind them: Speaking's
// GET /sessions/{id} scopes to a user only when a userId query parameter is
// supplied, and the browser was the thing supplying it. Omit it and the
// endpoint returns any user's transcript and evaluation by session id. Sourcing
// userId from the validated JWT here closes that, because the caller no longer
// controls the value.
type SpeakingHandler struct {
	httpClient         *http.Client
	speakingServiceURL string
	internalAPIKey     string
}

func NewSpeakingHandler(httpClient *http.Client, speakingServiceURL, internalAPIKey string) *SpeakingHandler {
	return &SpeakingHandler{
		httpClient:         httpClient,
		speakingServiceURL: speakingServiceURL,
		internalAPIKey:     internalAPIKey,
	}
}

// ListSessions proxies GET /sessions?userId=<from the token>.
func (h *SpeakingHandler) ListSessions(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	upstreamURL, err := url.Parse(h.speakingServiceURL + "/sessions")
	if err != nil {
		return err
	}
	query := upstreamURL.Query()
	// From the token, never from c.Query("userId"). A caller-supplied value here
	// is a request to read someone else's history.
	query.Set("userId", userID)
	upstreamURL.RawQuery = query.Encode()

	return h.forward(c, http.MethodGet, upstreamURL.String(), nil)
}

// GetSession proxies GET /sessions/{id}, always scoped to the token's user.
//
// Speaking answers 404 rather than 403 for a session owned by someone else,
// which is deliberate: it keeps "does not exist", "not yours" and "malformed
// id" indistinguishable, so the endpoint cannot be used to enumerate ids.
func (h *SpeakingHandler) GetSession(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	upstreamURL, err := h.sessionURL(c.Params("sessionId"))
	if err != nil {
		return err
	}
	query := upstreamURL.Query()
	query.Set("userId", userID)
	upstreamURL.RawQuery = query.Encode()

	return h.forward(c, http.MethodGet, upstreamURL.String(), nil)
}

// CreateShareLink proxies POST /sessions/{id}/share.
func (h *SpeakingHandler) CreateShareLink(c *fiber.Ctx) error {
	if _, err := authenticatedUserID(c); err != nil {
		return err
	}
	upstreamURL, err := h.sessionURL(c.Params("sessionId"), "share")
	if err != nil {
		return err
	}
	return h.forward(c, http.MethodPost, upstreamURL.String(), bytes.NewReader(c.Body()))
}

// GetPublicSession proxies GET /sessions/public/{token}.
//
// Unauthenticated by design: the recipient of a share link has no account, so
// this route is registered OUTSIDE the JWT-protected /api group. The share
// token is the authorisation. It deliberately takes no userId from anywhere --
// adding a user scope would break the feature outright.
func (h *SpeakingHandler) GetPublicSession(c *fiber.Ctx) error {
	upstreamURL, err := url.Parse(h.speakingServiceURL)
	if err != nil {
		return err
	}
	shareToken := c.Params("token")
	if shareToken == "" {
		return fiber.NewError(fiber.StatusBadRequest, "share token is required")
	}
	upstreamURL.Path = path.Join(upstreamURL.Path, "sessions", "public", shareToken)

	return h.forward(c, http.MethodGet, upstreamURL.String(), nil)
}

func (h *SpeakingHandler) sessionURL(sessionID string, suffix ...string) (*url.URL, error) {
	if sessionID == "" {
		return nil, fiber.NewError(fiber.StatusBadRequest, "session id is required")
	}
	upstreamURL, err := url.Parse(h.speakingServiceURL)
	if err != nil {
		return nil, err
	}
	segments := append([]string{upstreamURL.Path, "sessions", sessionID}, suffix...)
	upstreamURL.Path = path.Join(segments...)
	return upstreamURL, nil
}

func (h *SpeakingHandler) forward(c *fiber.Ctx, method, target string, body io.Reader) error {
	req, err := downstream.NewRequest(c, method, target, body)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-API-Key", h.internalAPIKey)
	if contentType := c.Get(fiber.HeaderContentType); contentType != "" {
		req.Header.Set(fiber.HeaderContentType, contentType)
	}
	c.Locals(middleware.ContextKeyUpstream, "speaking")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact speaking service")
	}
	defer resp.Body.Close()

	payload, err := io.ReadAll(resp.Body)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to read speaking service response")
	}
	if contentType := resp.Header.Get(fiber.HeaderContentType); contentType != "" {
		c.Set(fiber.HeaderContentType, contentType)
	}
	return c.Status(resp.StatusCode).Send(payload)
}
