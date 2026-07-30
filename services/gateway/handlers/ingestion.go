package handlers

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
)

type IngestionMessageSender interface {
	SendMessage(context.Context, *sqs.SendMessageInput, ...func(*sqs.Options)) (*sqs.SendMessageOutput, error)
}

type ingestionRunRequest struct {
	Adapters   []string `json:"adapters"`
	Tier       int      `json:"tier"`
	DryRun     bool     `json:"dry_run"`
	MaxItems   int      `json:"max_items,omitempty"`
	MaxSeconds int      `json:"max_seconds,omitempty"`
}

var allowedIngestionAdapters = map[string]struct{}{
	"ielts_org":             {},
	"daad":                  {},
	"chevening":             {},
	"study_in_poland":       {},
	"stipendium_hungaricum": {},
	"masters_portal":        {},
	"visa_adapter":          {},
}

func AdminIngestionRun(sender IngestionMessageSender, queueURL string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		if sender == nil || strings.TrimSpace(queueURL) == "" {
			return c.Status(fiber.StatusServiceUnavailable).JSON(fiber.Map{
				"error": "ingestion trigger is not configured",
			})
		}
		var request ingestionRunRequest
		if len(c.Body()) > 0 {
			if err := c.BodyParser(&request); err != nil {
				return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "invalid JSON body"})
			}
		}
		if request.Tier != 0 && request.Tier != 1 && request.Tier != 2 {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "tier must be 1 or 2"})
		}
		if len(request.Adapters) == 0 {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "at least one ingestion adapter is required",
			})
		}
		for _, adapter := range request.Adapters {
			if _, ok := allowedIngestionAdapters[adapter]; !ok {
				return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
					"error": "unknown ingestion adapter: " + adapter,
				})
			}
		}
		if request.MaxItems < 0 || request.MaxSeconds < 0 {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "work budgets must be non-negative",
			})
		}
		if request.MaxSeconds > 0 && request.MaxSeconds <= 120 {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "max_seconds must exceed the 120-second shutdown safety margin",
			})
		}

		jobID := uuid.NewString()
		payload := map[string]any{
			"run_id":   jobID,
			"adapters": request.Adapters,
			"dry_run":  request.DryRun,
		}
		if request.Tier != 0 {
			payload["tier"] = request.Tier
		}
		if request.MaxItems != 0 {
			payload["max_items"] = request.MaxItems
		}
		if request.MaxSeconds != 0 {
			payload["max_seconds"] = request.MaxSeconds
		}
		body, err := json.Marshal(payload)
		if err != nil {
			return fiber.ErrInternalServerError
		}
		_, err = sender.SendMessage(c.UserContext(), &sqs.SendMessageInput{
			QueueUrl:    &queueURL,
			MessageBody: aws.String(string(body)),
			MessageAttributes: map[string]types.MessageAttributeValue{
				"job_id": {
					DataType:    stringPointer("String"),
					StringValue: &jobID,
				},
			},
		})
		if err != nil {
			return c.Status(fiber.StatusBadGateway).JSON(fiber.Map{
				"error": "failed to queue ingestion run",
			})
		}
		return c.Status(fiber.StatusAccepted).JSON(fiber.Map{
			"status": "accepted",
			"job_id": jobID,
		})
	}
}

func stringPointer(value string) *string {
	return &value
}
