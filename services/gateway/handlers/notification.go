package handlers

import (
	"fmt"
	"io"
	"net/http"
	"net/url"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/gofiber/fiber/v2"
)

type NotificationHandler struct {
	httpClient             *http.Client
	notificationServiceURL string
	internalAPIKey         string
}

func NewNotificationHandler(httpClient *http.Client, notificationServiceURL string, internalAPIKey string) *NotificationHandler {
	return &NotificationHandler{
		httpClient:             httpClient,
		notificationServiceURL: notificationServiceURL,
		internalAPIKey:         internalAPIKey,
	}
}

func (h *NotificationHandler) List(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	upstreamURL, err := url.Parse(h.notificationServiceURL + "/api/notifications")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid notification service url")
	}
	query := upstreamURL.Query()
	query.Set("userId", userID)
	upstreamURL.RawQuery = query.Encode()

	req, err := downstream.NewRequest(c, http.MethodGet, upstreamURL.String(), nil)
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "failed creating notification request")
	}
	req.Header.Set("X-User-ID", userID)
	if h.internalAPIKey != "" {
		req.Header.Set("X-Internal-Api-Key", h.internalAPIKey)
	}

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, fmt.Sprintf("failed calling notification service: %v", err))
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "failed reading notification response")
	}

	c.Set("Content-Type", "application/json")
	return c.Status(resp.StatusCode).Send(body)
}
