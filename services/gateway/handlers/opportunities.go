package handlers

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// OpportunitiesHandler exposes RAG's profile-matching through the Gateway
// (GOA-132), so opportunity search gains JWT auth, rate limiting and a
// correlation ID instead of being reachable only as a side effect of a chat
// turn.
type OpportunitiesHandler struct {
	httpClient     *http.Client
	ragServiceURL  string
	internalAPIKey string
}

func NewOpportunitiesHandler(httpClient *http.Client, ragServiceURL, internalAPIKey string) *OpportunitiesHandler {
	return &OpportunitiesHandler{
		httpClient:     httpClient,
		ragServiceURL:  ragServiceURL,
		internalAPIKey: internalAPIKey,
	}
}

// Query proxies POST /api/opportunities/query to RAG's POST /match.
//
// The upstream body is CONSTRUCTED here, not forwarded. RAG's MatchRequest
// carries exactly one field, userId, so forwarding the client's body would mean
// forwarding the only thing that must not be client-controlled. Building it from
// the validated token makes a forged body structurally impossible to exploit
// rather than merely checked for -- there is no code path in which the caller's
// bytes reach RAG.
func (h *OpportunitiesHandler) Query(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	payload, err := json.Marshal(map[string]string{"userId": userID})
	if err != nil {
		return err
	}

	req, err := downstream.NewRequest(c, http.MethodPost, h.ragServiceURL+"/match", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	req.Header.Set("X-Internal-API-Key", h.internalAPIKey)
	// RAG links its Langfuse spans off traceparent (app/core/trace_context.py);
	// dropping it would orphan every match trace behind the Gateway.
	if traceparent := c.Get("traceparent"); traceparent != "" {
		req.Header.Set("traceparent", traceparent)
	}
	c.Locals(middleware.ContextKeyUpstream, "rag")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact opportunity search")
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to read opportunity search response")
	}
	c.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	return c.Status(resp.StatusCode).Send(body)
}
