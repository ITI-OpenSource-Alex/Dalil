package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/gofiber/fiber/v2"
)

type fakeIngestionSender struct {
	input *sqs.SendMessageInput
	err   error
}

func (sender *fakeIngestionSender) SendMessage(
	_ context.Context,
	input *sqs.SendMessageInput,
	_ ...func(*sqs.Options),
) (*sqs.SendMessageOutput, error) {
	sender.input = input
	return &sqs.SendMessageOutput{}, sender.err
}

func TestAdminIngestionRunRequiresAdminKeyAndQueuesValidatedPayload(t *testing.T) {
	sender := &fakeIngestionSender{}
	app := fiber.New()
	admin := app.Group("/api/admin", middleware.AdminKey("admin-secret"))
	admin.Post("/ingestion/run", AdminIngestionRun(sender, "queue-url"))

	body := []byte(`{"adapters":["visa_adapter"],"tier":2,"dry_run":true,"max_items":5}`)
	unauthenticated := httptest.NewRequest(
		fiber.MethodPost,
		"/api/admin/ingestion/run",
		bytes.NewReader(body),
	)
	unauthenticated.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	response, err := app.Test(unauthenticated)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.StatusCode)
	}

	authenticated := httptest.NewRequest(
		fiber.MethodPost,
		"/api/admin/ingestion/run",
		bytes.NewReader(body),
	)
	authenticated.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
	authenticated.Header.Set("X-Admin-Key", "admin-secret")
	response, err = app.Test(authenticated)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusAccepted {
		t.Fatalf("expected 202, got %d", response.StatusCode)
	}
	if sender.input == nil || sender.input.MessageBody == nil {
		t.Fatal("expected an SQS message")
	}
	var event map[string]any
	if err := json.Unmarshal([]byte(*sender.input.MessageBody), &event); err != nil {
		t.Fatal(err)
	}
	if event["tier"] != float64(2) || event["dry_run"] != true {
		t.Fatalf("unexpected event: %#v", event)
	}
	if event["run_id"] == "" {
		t.Fatal("expected a job/run id")
	}
}

func TestAdminIngestionRunRejectsUnknownAdapter(t *testing.T) {
	sender := &fakeIngestionSender{}
	app := fiber.New()
	app.Post("/run", AdminIngestionRun(sender, "queue-url"))
	request := httptest.NewRequest(
		fiber.MethodPost,
		"/run",
		bytes.NewBufferString(`{"adapters":["typo"]}`),
	)
	request.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)

	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusBadRequest {
		t.Fatalf("expected 400, got %d", response.StatusCode)
	}
	if sender.input != nil {
		t.Fatal("invalid request must not be queued")
	}
}

func TestAdminIngestionRunRejectsBudgetInsideSafetyMargin(t *testing.T) {
	sender := &fakeIngestionSender{}
	app := fiber.New()
	app.Post("/run", AdminIngestionRun(sender, "queue-url"))
	request := httptest.NewRequest(
		fiber.MethodPost,
		"/run",
		bytes.NewBufferString(`{"adapters":["masters_portal"],"max_seconds":120}`),
	)
	request.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)

	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusBadRequest {
		t.Fatalf("expected 400, got %d", response.StatusCode)
	}
	if sender.input != nil {
		t.Fatal("an unusable work budget must not be queued")
	}
}

func TestAdminIngestionRunRejectsMissingScope(t *testing.T) {
	sender := &fakeIngestionSender{}
	app := fiber.New()
	app.Post("/run", AdminIngestionRun(sender, "queue-url"))
	request := httptest.NewRequest(
		fiber.MethodPost,
		"/run",
		bytes.NewBufferString(`{"dry_run":true}`),
	)
	request.Header.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)

	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != fiber.StatusBadRequest {
		t.Fatalf("expected 400, got %d", response.StatusCode)
	}
	if sender.input != nil {
		t.Fatal("an unscoped run must not be queued")
	}
}
