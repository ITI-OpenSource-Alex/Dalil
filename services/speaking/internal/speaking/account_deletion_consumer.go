package speaking

import (
	"context"
	"encoding/json"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/rs/zerolog/log"
)

type accountDeletedEnvelope struct {
	Type    string `json:"Type"`
	Message string `json:"Message"`
}

type accountDeletedEvent struct {
	Type    string `json:"type"`
	Payload struct {
		UserID string `json:"userId"`
	} `json:"payload"`
}

func parseAccountDeletedUserID(body string) (string, bool) {
	raw := body
	var envelope accountDeletedEnvelope
	if err := json.Unmarshal([]byte(body), &envelope); err == nil && envelope.Type == "Notification" && envelope.Message != "" {
		raw = envelope.Message
	}

	var event accountDeletedEvent
	if err := json.Unmarshal([]byte(raw), &event); err != nil {
		return "", false
	}
	if event.Type != "account.deleted" || event.Payload.UserID == "" {
		return "", false
	}
	return event.Payload.UserID, true
}

func StartAccountDeletedConsumer(ctx context.Context, cfg *Config, repo db.Repository) {
	if cfg.AccountDeletedQueueName == "" {
		log.Warn().Msg("AccountDeleted queue not configured for speaking service")
		return
	}

	go func() {
		client, queueURL, err := speakingSQSClient(ctx, cfg)
		if err != nil {
			log.Error().Err(err).Msg("Unable to initialize speaking AccountDeleted SQS consumer")
			return
		}

		for {
			select {
			case <-ctx.Done():
				log.Info().Msg("Speaking AccountDeleted consumer stopped")
				return
			default:
			}

			output, err := client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
				QueueUrl:            aws.String(queueURL),
				MaxNumberOfMessages: 10,
				WaitTimeSeconds:     20,
			})
			if err != nil {
				log.Error().Err(err).Msg("Speaking AccountDeleted receive failed")
				waitForRetry(ctx)
				continue
			}

			for _, message := range output.Messages {
				if userID, ok := parseAccountDeletedUserID(aws.ToString(message.Body)); ok {
					var interviewDeleted int64
					if interviewRepo, ok := repo.(interface {
						DeleteInterviewsByUser(context.Context, string) (int64, error)
					}); ok {
						interviewDeleted, err = interviewRepo.DeleteInterviewsByUser(ctx, userID)
						if err != nil {
							log.Error().Err(err).Str("user_id", userID).Msg("Speaking interview AccountDeleted purge failed")
							continue
						}
					}
					deleted, err := repo.DeleteByUser(ctx, userID)
					if err != nil {
						log.Error().Err(err).Str("user_id", userID).Msg("Speaking AccountDeleted purge failed")
						continue
					}
					log.Info().Str("user_id", userID).Int64("deleted", deleted+interviewDeleted).Msg("Purged speaking data for deleted account")
				}

				if _, err := client.DeleteMessage(ctx, &sqs.DeleteMessageInput{
					QueueUrl:      aws.String(queueURL),
					ReceiptHandle: message.ReceiptHandle,
				}); err != nil {
					log.Error().Err(err).Msg("Speaking AccountDeleted delete-message failed")
				}
			}
		}
	}()
}

func speakingSQSClient(ctx context.Context, cfg *Config) (*sqs.Client, string, error) {
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.AWSRegion))
	if err != nil {
		return nil, "", err
	}
	client := sqs.NewFromConfig(awsCfg, func(options *sqs.Options) {
		if cfg.AWSEndpointURL != "" {
			options.BaseEndpoint = aws.String(cfg.AWSEndpointURL)
		}
	})
	output, err := client.GetQueueUrl(ctx, &sqs.GetQueueUrlInput{QueueName: aws.String(cfg.AccountDeletedQueueName)})
	if err != nil {
		return nil, "", err
	}
	return client, aws.ToString(output.QueueUrl), nil
}

func waitForRetry(ctx context.Context) {
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}
