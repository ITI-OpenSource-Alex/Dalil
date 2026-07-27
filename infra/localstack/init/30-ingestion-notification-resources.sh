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
create_queue_with_dlq "ingestion-queue"

# ING-02: the ingestion run writes its completion report here.
awslocal s3api create-bucket --bucket "$REPORTS_BUCKET" >/dev/null 2>&1 || true
