package handlers

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
	"github.com/valyala/fasthttp"
)

// StreamHandler proxies the two long-lived HTTP paths: Orchestration's chat SSE
// and the Writing service's per-essay evaluation SSE.
//
// These cannot reuse ExamHandler.forward, which does io.ReadAll on the upstream
// body. Buffering a stream to completion before sending it defeats the entire
// point — the client would receive every token at once, after the wait, which is
// exactly the failure GOA-096's ORC-08 exists to catch.
type StreamHandler struct {
	httpClient           *http.Client
	orchestrationBaseURL string
	writingBaseURL       string
	internalAPIKey       string
}

func NewStreamHandler(
	httpClient *http.Client,
	orchestrationBaseURL string,
	writingBaseURL string,
	internalAPIKey string,
) *StreamHandler {
	return &StreamHandler{
		httpClient:           httpClient,
		orchestrationBaseURL: orchestrationBaseURL,
		writingBaseURL:       writingBaseURL,
		internalAPIKey:       internalAPIKey,
	}
}

// Chat proxies POST /api/chat to Orchestration's SSE endpoint.
//
// The frontend previously posted to a relative /api/chat, i.e. to the Next.js
// server itself, where no route handler had ever been written — so it 404'd and
// surfaced as "Service unavailable" (BUG-044).
//
// userId is taken from the validated JWT, not the request body.
func (h *StreamHandler) Chat(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	payload := map[string]any{}
	if len(bytes.TrimSpace(c.Body())) > 0 {
		if err := json.Unmarshal(c.Body(), &payload); err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "invalid JSON body")
		}
	}
	payload["userId"] = userID
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	return h.stream(c, http.MethodPost, h.orchestrationBaseURL+"/chat", bytes.NewReader(body), "orchestration")
}

// ChatHistory proxies GET /api/chat/sessions/{sessionId}/history. Not a stream,
// but it lives with Chat so the two halves of the chat contract stay together.
func (h *StreamHandler) ChatHistory(c *fiber.Ctx) error {
	if _, err := authenticatedUserID(c); err != nil {
		return err
	}
	target, err := url.JoinPath(h.orchestrationBaseURL, "sessions", c.Params("sessionId"), "history")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid session id")
	}
	return h.stream(c, http.MethodGet, target, nil, "orchestration")
}

// WritingEvaluate proxies POST /api/writing/essays/{essayId}/evaluate, the
// per-criterion SSE stream.
//
// Orchestration hands the browser this essay id inside a writing_url event; it
// used to point at http://writing:8000 directly, a hostname no browser can
// resolve (BUG-016).
func (h *StreamHandler) WritingEvaluate(c *fiber.Ctx) error {
	if _, err := authenticatedUserID(c); err != nil {
		return err
	}
	target, err := url.JoinPath(h.writingBaseURL, "essays", c.Params("essayId"), "evaluate")
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid essay id")
	}
	return h.stream(c, http.MethodPost, target, bytes.NewReader(c.Body()), "writing")
}

// stream copies an upstream response to the client incrementally.
//
// SetBodyStreamWriter hands us a *bufio.Writer that fasthttp flushes as we fill
// it, so tokens reach the browser as they arrive upstream. The explicit Flush
// after every chunk is what makes that true — without it the data sits in the
// buffer until it fills, which reintroduces exactly the batching this handler
// exists to avoid.
func (h *StreamHandler) stream(
	c *fiber.Ctx,
	method string,
	target string,
	body io.Reader,
	upstreamName string,
) error {
	req, err := downstream.NewRequest(c, method, target, body)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-API-Key", h.internalAPIKey)
	if contentType := c.Get(fiber.HeaderContentType); contentType != "" {
		req.Header.Set(fiber.HeaderContentType, contentType)
	}
	req.Header.Set(fiber.HeaderAccept, "text/event-stream")
	c.Locals(middleware.ContextKeyUpstream, upstreamName)

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact "+upstreamName+" service")
	}

	c.Status(resp.StatusCode)
	if ct := resp.Header.Get(fiber.HeaderContentType); ct != "" {
		c.Set(fiber.HeaderContentType, ct)
	}
	// Proxies and browsers will happily buffer an event stream unless told not
	// to, which would undo the streaming for reasons invisible from the code.
	c.Set("Cache-Control", "no-cache")
	c.Set("X-Accel-Buffering", "no")

	// Capture the connection now: by the time the body-stream writer below runs,
	// the handler has returned and c has been recycled by Fiber.
	conn := c.Context().Conn()

	c.Context().SetBodyStreamWriter(fasthttp.StreamWriter(func(w *bufio.Writer) {
		defer resp.Body.Close()

		// Lift the write deadline for this connection only.
		//
		// The server sets WriteTimeout globally (10s), and fasthttp applies it to
		// the whole response, streamed body included. That silently severed this
		// proxy mid-stream: orchestration logged "status": success at 18.2s having
		// emitted 231 token events, while the client got the metadata frame and
		// nothing else. A truncated stream carrying a 200 and no error anywhere is
		// close to undiagnosable from the outside.
		//
		// This has to happen *here*, not in the handler. fasthttp sets the deadline
		// after the handler returns and immediately before it writes the response,
		// so a deadline cleared earlier is simply overwritten. This closure runs
		// during that write, which is the only point at which the clear survives.
		//
		// Raising WriteTimeout globally would weaken slow-client protection on
		// every other route, so it is lifted per-connection instead.
		if conn != nil {
			_ = conn.SetWriteDeadline(time.Time{})
		}

		buf := make([]byte, 4096)
		for {
			n, readErr := resp.Body.Read(buf)
			if n > 0 {
				if _, writeErr := w.Write(buf[:n]); writeErr != nil {
					return
				}
				// Flush every chunk. Without this the data sits in the buffer until
				// it fills, reintroducing the batching this handler exists to avoid.
				if flushErr := w.Flush(); flushErr != nil {
					return
				}
			}
			if readErr != nil {
				return
			}
		}
	}))

	return nil
}
