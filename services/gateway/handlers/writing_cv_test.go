package handlers

import (
	"bytes"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func TestUploadCVForwardsAuthenticatedUserAndFileMetadata(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/cv/upload" {
			t.Fatalf("unexpected upstream path %q", r.URL.Path)
		}
		if err := r.ParseMultipartForm(1024); err != nil {
			t.Fatalf("failed to parse upstream form: %v", err)
		}
		if got := r.FormValue("userId"); got != "user-123" {
			t.Fatalf("expected authenticated user ID, got %q", got)
		}
		file, header, err := r.FormFile("file")
		if err != nil {
			t.Fatalf("missing forwarded file: %v", err)
		}
		defer file.Close()
		if header.Filename != "resume.pdf" {
			t.Fatalf("unexpected filename %q", header.Filename)
		}
		if header.Header.Get("Content-Type") != "application/pdf" {
			t.Fatalf("unexpected content type %q", header.Header.Get("Content-Type"))
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"cvId":1,"status":"processing"}`))
	}))
	defer upstream.Close()

	// A nil llmClient falls back to httpClient, which is what this upload test
	// wants — only the CV review route needs the longer-lived client.
	handler := NewWritingHandler(upstream.Client(), nil, upstream.URL)
	app := fiber.New()
	app.Post("/cv/upload", func(c *fiber.Ctx) error {
		c.Locals(middleware.ContextKeyUserID, "user-123")
		return handler.UploadCV(c)
	})

	request := newCVUploadRequest(t)
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", response.StatusCode)
	}
	body, _ := io.ReadAll(response.Body)
	if string(body) != `{"cvId":1,"status":"processing"}` {
		t.Fatalf("unexpected response %s", body)
	}
}

func newCVUploadRequest(t *testing.T) *http.Request {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	partHeader := make(map[string][]string)
	partHeader["Content-Disposition"] = []string{`form-data; name="file"; filename="resume.pdf"`}
	partHeader["Content-Type"] = []string{"application/pdf"}
	part, err := writer.CreatePart(partHeader)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = part.Write([]byte("%PDF-1.7"))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/cv/upload", &body)
	request.Header.Set("Content-Type", writer.FormDataContentType())
	return request
}
