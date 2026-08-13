package handlers

import (
	"bytes"
	"encoding/json"
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
	return h.forwardWith(c, method, target, body, nil)
}

// forwardWith is forward plus headers set on the *outbound* request.
//
// downstream.NewRequest builds a fresh http.Request and copies only the
// correlation ID, so setting a header on the inbound fiber.Ctx does not reach
// the upstream at all -- it is silently dropped, and an endpoint with a required
// header answers 422 for reasons nothing in the gateway explains.
func (h *ExamHandler) forwardWith(
	c *fiber.Ctx,
	method string,
	target string,
	body io.Reader,
	extraHeaders map[string]string,
) error {
	req, err := downstream.NewRequest(c, method, target, body)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-API-Key", h.internalAPIKey)
	for name, value := range extraHeaders {
		req.Header.Set(name, value)
	}
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

// The four session routes the frontend previously called directly on :8085,
// carrying INTERNAL_API_KEY in a NEXT_PUBLIC_ variable — i.e. published to every
// browser (BUG-046). Behind the gateway the key stays server-side, and these
// paths pick up JWT auth, rate limiting and correlation IDs like everything else.
//
// user_id is taken from the validated JWT rather than the request, so a caller
// cannot read or submit another candidate's session by editing a payload.

func (h *ExamHandler) CreateSession(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	body, err := withUserID(c.Body(), userID)
	if err != nil {
		return err
	}

	return h.forward(
		c,
		http.MethodPost,
		h.examServiceURL+"/sessions",
		bytes.NewReader(body),
	)
}

func (h *ExamHandler) GetSession(c *fiber.Ctx) error {
	if _, err := authenticatedUserID(c); err != nil {
		return err
	}
	target, err := h.sessionURL(c.Params("sessionId"), "")
	if err != nil {
		return err
	}
	return h.forward(c, http.MethodGet, target, nil)
}

func (h *ExamHandler) SubmitSession(c *fiber.Ctx) error {
	if _, err := authenticatedUserID(c); err != nil {
		return err
	}
	target, err := h.sessionURL(c.Params("sessionId"), "submit")
	if err != nil {
		return err
	}
	return h.forward(c, http.MethodPut, target, bytes.NewReader(c.Body()))
}

func (h *ExamHandler) GetSessionResult(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	target, err := h.sessionURL(c.Params("sessionId"), "result")
	if err != nil {
		return err
	}
	return h.forwardWith(c, http.MethodGet, target, nil, map[string]string{
		"X-User-Id": userID,
	})
}

// GetProgress returns the authenticated candidate's score trends. The user ID
// comes from the JWT, never from a browser-controlled URL parameter.
func (h *ExamHandler) GetProgress(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	target, err := url.JoinPath(h.examServiceURL, "users", userID, "progress")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid user id")
	}
	return h.forward(c, http.MethodGet, target, nil)
}

// GetHistory proxies GET /api/exam/history to the Exam service's
// GET /users/{id}/exam-history, which has existed since the history/progress
// work landed but had no gateway route in front of it -- unreachable from the
// browser even though the endpoint and its response schema (ExamHistoryItem)
// were already implemented. The user ID comes from the JWT, matching every
// other route in this file; `page` passes through unchanged when present so
// the existing 20-rows-per-page pagination on the Exam service works as-is.
func (h *ExamHandler) GetHistory(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	target, err := url.JoinPath(h.examServiceURL, "users", userID, "exam-history")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid user id")
	}
	if page := c.Query("page"); page != "" {
		parsed, err := url.Parse(target)
		if err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "invalid user id")
		}
		query := parsed.Query()
		query.Set("page", page)
		parsed.RawQuery = query.Encode()
		target = parsed.String()
	}
	return h.forward(c, http.MethodGet, target, nil)
}

// GetWeakAreas proxies GET /api/exam/weak-areas to the Exam service's
// GET /users/{id}/weak-areas -- same unreachable-endpoint situation as
// GetHistory above.
func (h *ExamHandler) GetWeakAreas(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	target, err := url.JoinPath(h.examServiceURL, "users", userID, "weak-areas")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid user id")
	}
	return h.forward(c, http.MethodGet, target, nil)
}

// SubmitReadingSession proxies PUT /api/exam/reading/{sessionId}/submit.
//
// The generic SubmitSession above hits the exam service's generic
// PUT /sessions/:id/submit, which only returns {session_id, status,
// raw_score, band_score} -- no per_question_result, no section_breakdown.
// GOA-055's results page (per-question review, question-type breakdown,
// section progress bars) needs that data, which only the Reading-specific
// PUT /exam/reading/:id/submit endpoint returns. There was previously no
// gateway route for it at all, so the frontend called the exam service
// directly on :8085 with INTERNAL_API_KEY published to the browser --
// exactly the BUG-046 exposure this gateway migration exists to close.
func (h *ExamHandler) SubmitReadingSession(c *fiber.Ctx) error {
	if _, err := authenticatedUserID(c); err != nil {
		return err
	}
	target, err := url.JoinPath(
		h.examServiceURL, "exam", "reading", c.Params("sessionId"), "submit",
	)
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid session id")
	}
	return h.forward(c, http.MethodPut, target, bytes.NewReader(c.Body()))
}

// Heartbeat proxies PATCH /api/exam/sessions/{id}/heartbeat.
//
// The exam service has had this endpoint since GOA-092 and nothing has ever
// called it -- there was no gateway route to reach it through and no client code
// that tried. Meanwhile the sweep abandons sessions that stop reporting, so the
// missing caller was not a gap in telemetry but the thing standing between a
// candidate and losing their exam (BUG-054).
//
// X-User-Id comes from the validated JWT. The upstream 403s when it does not
// match the session owner, so sourcing it from the token rather than the request
// is what stops one candidate keeping another's session alive.
func (h *ExamHandler) Heartbeat(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	target, err := h.sessionURL(c.Params("sessionId"), "heartbeat")
	if err != nil {
		return err
	}
	return h.forwardWith(c, http.MethodPatch, target, nil, map[string]string{
		"X-User-Id": userID,
	})
}

// sessionURL builds /sessions/{id}[/suffix]. url.JoinPath escapes the id, so a
// path-traversal attempt in the parameter cannot reach a different upstream
// route.
func (h *ExamHandler) sessionURL(sessionID string, suffix string) (string, error) {
	segments := []string{"sessions", sessionID}
	if suffix != "" {
		segments = append(segments, suffix)
	}
	target, err := url.JoinPath(h.examServiceURL, segments...)
	if err != nil {
		return "", fiber.NewError(fiber.StatusBadRequest, "invalid session id")
	}
	return target, nil
}

// withUserID overwrites user_id in a JSON body with the authenticated user's id,
// adding it when absent. The exam service requires the field; taking it from the
// token rather than trusting the client is what stops a caller opening a session
// as somebody else.
func withUserID(body []byte, userID string) ([]byte, error) {
	payload := map[string]any{}
	if len(bytes.TrimSpace(body)) > 0 {
		if err := json.Unmarshal(body, &payload); err != nil {
			return nil, fiber.NewError(fiber.StatusBadRequest, "invalid JSON body")
		}
	}
	payload["user_id"] = userID
	return json.Marshal(payload)
}
