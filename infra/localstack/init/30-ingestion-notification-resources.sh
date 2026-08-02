#!/bin/sh
set -eu

# GOA-103/INFRA-07 requires notification-queue and ingestion-queue to exist WITH
# DLQs, and GOA-105/EVT-06 asserts nothing is stuck in any DLQ — an assertion that
# passes vacuously when the DLQ does not exist. GOA-024's scholarship matcher also
# publishes to notification-queue and silently no-ops without NOTIFICATION_QUEUE_URL.
#
# Redrive settings mirror 20-user-events-resources.sh so local behaviour matches
# infra/terraform/locals.tf rather than drifting from it.

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"
REPORTS_BUCKET="goa-ingestion-reports"
# GOA-083: the notification service sends auth emails via SES. Without verifying
# the sender at startup, every SendEmail is rejected — the poller records
# batchItemFailures, the message is redelivered, and it eventually lands in the
# DLQ. Verifying here makes the E2E flow reproducible from a cold docker compose
# up without a manual step.
SES_SENDER="${SES_SENDER_ADDRESS:-notifications@localhost.test}"

create_queue_with_dlq() {
  queue_name="$1"
  dlq_name="${queue_name}-dlq"

  awslocal sqs create-queue \
    --queue-name "$dlq_name" \
    --attributes "{\"MessageRetentionPeriod\":\"1209600\"}" \
    >/dev/null

  dlq_arn="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${dlq_name}"

  awslocal sqs create-queue \
    --queue-name "$queue_name" \
    --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
    >/dev/null
}

create_queue_with_dlq "notification-queue"

# An ingestion item may use the full bounded worker window. Keep its message
# invisible while the task is alive so a second consumer cannot duplicate spend.
awslocal sqs create-queue \
  --queue-name "ingestion-queue-dlq" \
  --attributes "{\"MessageRetentionPeriod\":\"1209600\"}" \
  >/dev/null
awslocal sqs create-queue \
  --queue-name "ingestion-queue" \
  --attributes "{\"VisibilityTimeout\":\"4320\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"arn:aws:sqs:${REGION}:${ACCOUNT_ID}:ingestion-queue-dlq\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
  >/dev/null

# ING-02: the ingestion run writes its completion report here.
awslocal s3api create-bucket --bucket "$REPORTS_BUCKET" >/dev/null 2>&1 || true

# GOA-083: verify the SES sender identity so the notification service can send.
# Idempotent, and tolerant if SES is not in the SERVICES list on some setups.
awslocal ses verify-email-identity --email-address "$SES_SENDER" >/dev/null 2>&1 \
  || echo "warn: could not verify SES identity ${SES_SENDER} (is 'ses' in SERVICES?)"
