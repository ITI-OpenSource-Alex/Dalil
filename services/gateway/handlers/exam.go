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

type ExamHandler struct {
	httpClient     *http.Client
	examServiceURL string
	internalAPIKey string
}

func NewExamHandler(httpClient *http.Client, examServiceURL string, internalAPIKey string) *ExamHandler {
	return &ExamHandler{
		httpClient:     httpClient,
		examServiceURL: examServiceURL,
		internalAPIKey: internalAPIKey,
	}
}

func (h *ExamHandler) StartListening(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	upstreamURL, err := url.Parse(h.examServiceURL + "/exam/listening/start")
	if err != nil {
		return err
	}
	query := upstreamURL.Query()
	query.Set("user_id", userID)
	examType := c.Query("exam_type", "academic")
	query.Set("exam_type", examType)
	upstreamURL.RawQuery = query.Encode()

	return h.forward(c, http.MethodGet, upstreamURL.String(), nil)
}

func (h *ExamHandler) SubmitListening(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	upstreamURL, err := url.Parse(h.examServiceURL)
	if err != nil {
		return err
	}
	upstreamURL.Path = path.Join(
		upstreamURL.Path,
		"exam/listening",
		c.Params("sessionId"),
		"submit",
	)
	query := upstreamURL.Query()
	query.Set("user_id", userID)
	upstreamURL.RawQuery = query.Encode()

	return h.forward(
		c,
		http.MethodPut,
		upstreamURL.String(),
		bytes.NewReader(c.Body()),
	)
}

func (h *ExamHandler) forward(c *fiber.Ctx, method string, target string, body io.Reader) error {
	req, err := downstream.NewRequest(c, method, target, body)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-API-Key", h.internalAPIKey)
	if contentType := c.Get(fiber.HeaderContentType); contentType != "" {
		req.Header.Set(fiber.HeaderContentType, contentType)
	}
	c.Locals(middleware.ContextKeyUpstream, "exam")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact exam service")
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	c.Status(resp.StatusCode)
	c.Set(fiber.HeaderContentType, resp.Header.Get(fiber.HeaderContentType))
	return c.Send(responseBody)
}

func authenticatedUserID(c *fiber.Ctx) (string, error) {
	userID, ok := c.Locals(middleware.ContextKeyUserID).(string)
	if !ok || userID == "" {
		return "", fiber.NewError(fiber.StatusUnauthorized, "unauthorized")
	}
	return userID, nil
}
