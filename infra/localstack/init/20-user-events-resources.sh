#!/bin/sh
set -eu

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"
QUEUE="user-events"
DLQ="user-events-dlq"

# Matches infra/terraform/locals.tf's user_events queue definition (visibility_timeout_seconds = 30,
# max_receive_count = 3) and infra/terraform/modules/sqs/main.tf (DLQ retains messages for 14 days,
# primary queue's redrive_policy points at the DLQ).
awslocal sqs create-queue \
  --queue-name "$DLQ" \
  --attributes "{\"MessageRetentionPeriod\":\"1209600\"}" \
  >/dev/null

DLQ_ARN="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${DLQ}"

awslocal sqs create-queue \
  --queue-name "$QUEUE" \
  --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
  >/dev/null
