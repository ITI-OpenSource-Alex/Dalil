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
