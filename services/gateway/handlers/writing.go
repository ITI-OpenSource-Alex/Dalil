package handlers

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
	"github.com/valyala/fasthttp"
)

type WritingHandler struct {
	httpClient        *http.Client
	llmClient         *http.Client
	writingServiceURL string
}

// NewWritingHandler takes two clients on purpose.
//
// httpClient carries the shared 10s timeout, which is right for uploads and
// keeps slow-client protection on those routes. llmClient is for routes that
// wait on a model: CV review is a full LLM call and cannot finish in 10s, so on
// the shared client it returned 502 at exactly 10.007s while the writing
// service was still working — a gateway timeout wearing the costume of an
// upstream failure.
func NewWritingHandler(httpClient *http.Client, llmClient *http.Client, writingServiceURL string) *WritingHandler {
	if llmClient == nil {
		llmClient = httpClient
	}
	return &WritingHandler{
		httpClient:        httpClient,
		llmClient:         llmClient,
		writingServiceURL: writingServiceURL,
	}
}

func (h *WritingHandler) UploadEssay(c *fiber.Ctx) error {
	form, err := c.MultipartForm()
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid multipart form data")
	}

	essayTexts := form.Value["essayText"]
	submissionTypes := form.Value["submissionType"]
	examSessionIDs := form.Value["examSessionId"]

	if len(essayTexts) == 0 {
		return fiber.NewError(fiber.StatusBadRequest, "essayText is required")
	}
	if len(submissionTypes) == 0 {
		return fiber.NewError(fiber.StatusBadRequest, "submissionType is required")
	}

	essayText := essayTexts[0]
	submissionType := submissionTypes[0]

	var examSessionID string
	if len(examSessionIDs) > 0 {
		examSessionID = examSessionIDs[0]
	}

	userID, ok := c.Locals(middleware.ContextKeyUserID).(string)
	if !ok || userID == "" {
		return fiber.NewError(fiber.StatusUnauthorized, "unauthorized")
	}

	var requestBody bytes.Buffer
	writer := multipart.NewWriter(&requestBody)

	if err := writer.WriteField("userId", userID); err != nil {
		return err
	}
	if err := writer.WriteField("essayText", essayText); err != nil {
		return err
	}
	if err := writer.WriteField("submissionType", submissionType); err != nil {
		return err
	}
	if examSessionID != "" {
		if err := writer.WriteField("examSessionId", examSessionID); err != nil {
			return err
		}
	}

	files := form.File["file"]
	if len(files) > 0 {
		fileHeader := files[0]

		src, err := fileHeader.Open()
		if err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "failed to read uploaded file")
		}
		defer src.Close()

		part, err := writer.CreateFormFile("file", fileHeader.Filename)
		if err != nil {
			return err
		}

		if _, err := io.Copy(part, src); err != nil {
			return err
		}
	}

	if err := writer.Close(); err != nil {
		return err
	}

	req, err := downstream.NewRequest(
		c,
		http.MethodPost,
		h.writingServiceURL+"/essays/upload",
		&requestBody,
	)
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	c.Status(resp.StatusCode)
	c.Set(fiber.HeaderContentType, resp.Header.Get("Content-Type"))

	return c.Send(responseBody)
}

// UploadCV forwards a CV using the authenticated user ID from the JWT context.
// Client-provided userId values are deliberately ignored.
func (h *WritingHandler) UploadCV(c *fiber.Ctx) error {
	form, err := c.MultipartForm()
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid multipart form data")
	}

	files := form.File["file"]
	if len(files) == 0 {
		return fiber.NewError(fiber.StatusBadRequest, "file is required")
	}

	userID, ok := c.Locals(middleware.ContextKeyUserID).(string)
	if !ok || userID == "" {
		return fiber.NewError(fiber.StatusUnauthorized, "unauthorized")
	}

	fileHeader := files[0]
	src, err := fileHeader.Open()
	if err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "failed to read uploaded file")
	}
	defer src.Close()

	var requestBody bytes.Buffer
	writer := multipart.NewWriter(&requestBody)
	if err := writer.WriteField("userId", userID); err != nil {
		return err
	}

	filename := filepath.Base(strings.ReplaceAll(fileHeader.Filename, "\\", "/"))
	partHeader := make(textproto.MIMEHeader)
	partHeader.Set(
		"Content-Disposition",
		fmt.Sprintf(`form-data; name="file"; filename="%s"`, strings.ReplaceAll(filename, `"`, `\"`)),
	)
	contentType := fileHeader.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	partHeader.Set("Content-Type", contentType)
	part, err := writer.CreatePart(partHeader)
	if err != nil {
		return err
	}
	if _, err := io.Copy(part, src); err != nil {
		return err
	}
	if err := writer.Close(); err != nil {
		return err
	}

	req, err := downstream.NewRequest(
		c,
		http.MethodPost,
		h.writingServiceURL+"/cv/upload",
		&requestBody,
	)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	c.Status(resp.StatusCode)
	c.Set(fiber.HeaderContentType, resp.Header.Get("Content-Type"))
	return c.Send(responseBody)
}

// ListEssays proxies GET /api/writing/essays to the Writing service's new
// GET /essays -- a paged, user-scoped summary list. The essays table already
// held every submission a user has ever made (chat practice and exam tasks
// alike, distinguished by submission_type) with no way for the browser to
// list them; this is the read side of that data. userId comes from the JWT,
// never the query string, so a caller cannot list another user's essays by
// editing the request; page and submission_type pass through unchanged.
func (h *WritingHandler) ListEssays(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	target, err := url.Parse(h.writingServiceURL + "/essays")
	if err != nil {
		return err
	}
	query := target.Query()
	query.Set("user_id", userID)
	if page := c.Query("page"); page != "" {
		query.Set("page", page)
	}
	if submissionType := c.Query("submission_type"); submissionType != "" {
		query.Set("submission_type", submissionType)
	}
	target.RawQuery = query.Encode()

	req, err := downstream.NewRequest(c, http.MethodGet, target.String(), nil)
	if err != nil {
		return err
	}
	c.Locals(middleware.ContextKeyUpstream, "writing")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
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

// LatestCV proxies GET /api/writing/cv/latest -- the signed-in user's most
// recent upload, if any. Lets the Profile and programme checklist surfaces
// show upload/processing status and recover cvS3Key across a reload.
// Free-tier, same as ListEssays: reading your own upload status is not the
// paid step, POST /cv/review is.
func (h *WritingHandler) LatestCV(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	target, err := url.Parse(h.writingServiceURL + "/cv/latest")
	if err != nil {
		return err
	}
	query := target.Query()
	query.Set("userId", userID)
	target.RawQuery = query.Encode()

	req, err := downstream.NewRequest(c, http.MethodGet, target.String(), nil)
	if err != nil {
		return err
	}
	c.Locals(middleware.ContextKeyUpstream, "writing")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
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

// ReviewCV proxies POST /api/writing/cv/review.
//
// The writing service grew this endpoint alongside BUG-019; without a gateway
// route the browser still could not reach it, and the CV feature would have
// stayed a pipeline that produces structured data nothing consumes.
//
// userId comes from the validated JWT rather than the body. The writing service
// reads by (userId, cvS3Key), so taking userId from the token is what stops a
// caller reviewing someone else's CV by editing the payload.
func (h *WritingHandler) ReviewCV(c *fiber.Ctx) error {
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

	req, err := downstream.NewRequest(c, http.MethodPost, h.writingServiceURL+"/cv/review", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	c.Locals(middleware.ContextKeyUpstream, "writing")

	resp, err := h.llmClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
	}

	c.Status(resp.StatusCode)
	if ct := resp.Header.Get(fiber.HeaderContentType); ct != "" {
		c.Set(fiber.HeaderContentType, ct)
	}
	c.Set("Cache-Control", "no-cache")
	c.Set("X-Accel-Buffering", "no")

	conn := c.Context().Conn()
	c.Context().SetBodyStreamWriter(fasthttp.StreamWriter(func(w *bufio.Writer) {
		defer resp.Body.Close()
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

// --- Motivation letter review (per-programme admissions feedback) --------------
//
// Plain JSON proxies, not the SSE stream ReviewCV uses: the writing service returns
// the completed review in one response, so there is nothing to stream. userId is
// injected from the JWT here and never accepted from the browser, matching every
// other route in this file (BUG-046).

func (h *WritingHandler) CreateMotivationLetterReview(c *fiber.Ctx) error {
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

	req, err := downstream.NewRequest(c, http.MethodPost, h.writingServiceURL+"/motivation-letters", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	c.Locals(middleware.ContextKeyUpstream, "writing")

	// llmClient, not httpClient: five concurrent criterion agents run inside this
	// request and the default client timeout is sized for ordinary CRUD.
	resp, err := h.llmClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to read writing service response")
	}
	if ct := resp.Header.Get(fiber.HeaderContentType); ct != "" {
		c.Set(fiber.HeaderContentType, ct)
	}
	return c.Status(resp.StatusCode).Send(respBody)
}

func (h *WritingHandler) ListMotivationLetterReviews(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	target := h.writingServiceURL + "/motivation-letters?userId=" + url.QueryEscape(userID)
	if programID := c.Query("programId"); programID != "" {
		target += "&programId=" + url.QueryEscape(programID)
	}

	req, err := downstream.NewRequest(c, http.MethodGet, target, nil)
	if err != nil {
		return err
	}
	c.Locals(middleware.ContextKeyUpstream, "writing")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to read writing service response")
	}
	if ct := resp.Header.Get(fiber.HeaderContentType); ct != "" {
		c.Set(fiber.HeaderContentType, ct)
	}
	return c.Status(resp.StatusCode).Send(respBody)
}

func (h *WritingHandler) GetMotivationLetterReview(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	letterID := c.Params("id")
	target := h.writingServiceURL + "/motivation-letters/" + url.QueryEscape(letterID) + "?userId=" + url.QueryEscape(userID)

	req, err := downstream.NewRequest(c, http.MethodGet, target, nil)
	if err != nil {
		return err
	}
	c.Locals(middleware.ContextKeyUpstream, "writing")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to contact writing service")
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fiber.NewError(fiber.StatusBadGateway, "failed to read writing service response")
	}
	if ct := resp.Header.Get(fiber.HeaderContentType); ct != "" {
		c.Set(fiber.HeaderContentType, ct)
	}
	return c.Status(resp.StatusCode).Send(respBody)
}
