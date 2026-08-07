# GOA-091 User Events Fan-Out

## Shape

`user-events` is now an SNS topic. The old bare SQS queue is removed from the
Terraform queue map. Consumers receive raw JSON through dedicated subscriber
queues:

- `user-events-rag`
- `user-events-orchestration`
- `user-events-exam`
- `user-events-speaking`
- `user-events-writing`
- `user-events-notification`

Each subscriber queue has a `-dlq`, `visibility_timeout_seconds = 30`, and
`maxReceiveCount = 3`. SNS subscriptions use raw message delivery so consumers
receive the same JSON payloads used before GOA-091.

## Deploy Sequence

1. Apply Terraform to create the SNS topic, subscriber queues, DLQs,
   subscriptions, and queue policies.
2. Deploy RAG with `SQS_QUEUE_NAME=user-events-rag`.
3. Deploy User with `USER_EVENTS_TOPIC_ARN` and without the old
   `SQS_QUEUE_URL` user-events producer.
4. Confirm profile updates publish `UserUpdated` to all six subscriber queues.
5. Confirm RAG updates `LocalUserProfile` from `user-events-rag`.
6. Remove the old bare `user-events` SQS queue from state during the same plan.

## Terraform Plan Check

Run:

```powershell
$env:AWS_PROFILE="goa-production"
terraform plan --% -var-file=environments\staging.tfvars -lock=false -refresh=false -no-color
```

Expected destroy scope:

- `module.sqs.aws_sqs_queue.this["user_events"]`
- `module.sqs.aws_sqs_queue.dlq["user_events"]`
- `module.sqs.aws_sqs_queue_redrive_allow_policy.this["user_events"]`

No other destroys are expected.

## LocalStack Check

After `docker compose up localstack`, publish one profile event:

```powershell
awslocal sns publish --topic-arn arn:aws:sns:us-east-1:000000000000:user-events --message '{\"type\":\"user.updated\",\"version\":\"1.0\",\"timestamp\":\"2026-08-04T00:00:00Z\",\"correlationId\":\"00000000-0000-4000-8000-000000000000\",\"payload\":{\"userId\":\"local-user\",\"email\":\"local@example.com\",\"subscriptionTier\":\"free\"}}'
```

Then receive from each subscriber queue and confirm the body is the raw JSON,
not an SNS envelope.
