package handlers

import (
	"bytes"
	"io"
	"net/http"

	"github.com/gofiber/fiber/v2"
)

// ProfileHandler proxies GOA-035's "who am I" read to the User service, fixing
// BUG-047 for the pages that use it: the frontend previously had no way to fetch
// the authenticated user's real profile and fell back to a hardcoded id
// (lib/current-user.ts). GET /users/:id (users.controller.ts) already returns the
// user plus its profile relation and is InternalAuthGuard-protected, so this proxy
// supplies the internal key and the JWT-derived id -- no new User service endpoint
// is needed.
type ProfileHandler struct {
	httpClient     *http.Client
	userServiceURL string
	internalAPIKey string
}

func NewProfileHandler(httpClient *http.Client, userServiceURL string, internalAPIKey string) *ProfileHandler {
	return &ProfileHandler{
		httpClient:     httpClient,
		userServiceURL: userServiceURL,
		internalAPIKey: internalAPIKey,
	}
}

// GetProfile proxies GET /api/profile -> GET {userServiceURL}/users/:id, where :id
// is always the authenticated caller's own id, never a client-supplied value.
func (h *ProfileHandler) GetProfile(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(
		c.UserContext(), http.MethodGet, h.userServiceURL+"/users/"+userID, nil,
	)
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "internal request error")
	}
	req.Header.Set("X-Internal-Api-Key", h.internalAPIKey)

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact user service")
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	c.Status(resp.StatusCode)
	c.Set(fiber.HeaderContentType, resp.Header.Get(fiber.HeaderContentType))
	return c.Send(body)
}

// UpdateProfile proxies PUT /api/profile -> PUT {userServiceURL}/users/:id/profile
// (profiles.controller.ts), where :id is always the authenticated caller's own id,
// never a client-supplied value. Added for the onboarding wizard (GOA frontend
// Phase 3): the User service already implements this route and its validation;
// this handler only exposes it through the Gateway, the same proxy shape as
// GetProfile above. No User-service code changes.
func (h *ProfileHandler) UpdateProfile(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(
		c.UserContext(), http.MethodPut, h.userServiceURL+"/users/"+userID+"/profile", bytes.NewReader(c.Body()),
	)
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "internal request error")
	}
	req.Header.Set("X-Internal-Api-Key", h.internalAPIKey)
	req.Header.Set(fiber.HeaderContentType, "application/json")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact user service")
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	c.Status(resp.StatusCode)
	c.Set(fiber.HeaderContentType, resp.Header.Get(fiber.HeaderContentType))
	return c.Send(body)
}
