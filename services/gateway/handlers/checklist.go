package handlers

import (
	"bytes"
	"io"
	"net/http"
	"net/url"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// ChecklistHandler proxies GOA-084's checklist persistence endpoints to the RAG
// service. Unlike ExamHandler/WritingHandler, these routes carry no internal API
// key: the RAG service's /checklists endpoints (app/core/security.py's
// require_user_id) scope ownership entirely by X-User-ID, matching the design
// already used for /query, /score and /match.
type ChecklistHandler struct {
	httpClient    *http.Client
	ragServiceURL string
}

func NewChecklistHandler(httpClient *http.Client, ragServiceURL string) *ChecklistHandler {
	return &ChecklistHandler{httpClient: httpClient, ragServiceURL: ragServiceURL}
}

// GetChecklist proxies GET /api/checklists/:programId.
func (h *ChecklistHandler) GetChecklist(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	// url.JoinPath escapes programId, so a path-traversal attempt in the
	// parameter cannot reach a different upstream route (mirrors
	// ExamHandler.sessionURL).
	target, err := url.JoinPath(h.ragServiceURL, "checklists", c.Params("programId"))
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid program id")
	}

	return h.forward(c, http.MethodGet, target, nil, userID)
}

// UpdateChecklistItem proxies PUT /api/checklists/:programId/items/:itemId.
func (h *ChecklistHandler) UpdateChecklistItem(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	target, err := url.JoinPath(
		h.ragServiceURL, "checklists", c.Params("programId"), "items", c.Params("itemId"),
	)
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid program or item id")
	}

	return h.forward(c, http.MethodPut, target, bytes.NewReader(c.Body()), userID)
}

// GetChecklistFinancials proxies GET /api/checklists/:programId/financial.
// GOA-035: same ownership/forwarding shape as GetChecklist, hitting RAG's sibling
// /checklists/:programId/financial route (checklist_financial.py), which reads
// structured visa data (GOA-108) only -- no LLM in that path.
func (h *ChecklistHandler) GetChecklistFinancials(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	target, err := url.JoinPath(h.ragServiceURL, "checklists", c.Params("programId"), "financial")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid program id")
	}

	return h.forward(c, http.MethodGet, target, nil, userID)
}

// forward builds the downstream request, injects the authenticated user's id as
// X-User-ID -- taken from the validated JWT rather than any client-supplied value,
// so a caller can never read or mutate another user's checklist -- and relays the
// RAG service's response verbatim.
func (h *ChecklistHandler) forward(
	c *fiber.Ctx, method string, target string, body io.Reader, userID string,
) error {
	req, err := downstream.NewRequest(c, method, target, body)
	if err != nil {
		return err
	}
	req.Header.Set("X-User-ID", userID)
	if contentType := c.Get(fiber.HeaderContentType); contentType != "" {
		req.Header.Set(fiber.HeaderContentType, contentType)
	}
	c.Locals(middleware.ContextKeyUpstream, "rag")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact rag service")
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
