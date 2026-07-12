package handlers

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"path/filepath"
	"strings"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/downstream"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

type WritingHandler struct {
	httpClient        *http.Client
	writingServiceURL string
}

func NewWritingHandler(httpClient *http.Client, writingServiceURL string) *WritingHandler {
	return &WritingHandler{
		httpClient:        httpClient,
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
