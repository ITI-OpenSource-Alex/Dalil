#!/bin/sh
set -eu

# CV pipeline resources.
#
# Consumer status, deliberate as of 2026-07-27 (BUG-025):
#
#   goa-cv-processing  consumed by the cv-processor service; drains 0 -> 0
#                      across a full upload cycle.
#   goa-cv-uploaded    WRITE-ONLY. Nothing reads it.
#   goa-cv-processed   WRITE-ONLY. Nothing reads it.
#
# The two write-only queues grow without bound and that is expected, not a
# consumer outage -- do not go looking for a crashed worker. They were meant to
# feed a notification service; services/notification/ contains only a .gitkeep,
# so no such service has ever existed. Building it was scoped out rather than
# left ambiguous. If it is ever built, GOA-031 (Lambda migration) already lists
# a notification worker and is the natural home.

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"
BUCKET="goa-writing-files"
EXAM_AUDIO_BUCKET="goa-exam-audio"
DOMAIN_QUEUE="goa-cv-uploaded"
PROCESSOR_QUEUE="goa-cv-processing"
PROCESSED_QUEUE="goa-cv-processed"

awslocal s3api create-bucket --bucket "$BUCKET" >/dev/null 2>&1 || true
awslocal s3api create-bucket --bucket "$EXAM_AUDIO_BUCKET" >/dev/null 2>&1 || true

# Dead-letter queues for the three CV queues.
#
# These were the only queues in the system without one -- user-events,
# notification-queue and ingestion-queue all had a DLQ from the start, so a
# poison message on goa-cv-processing had nowhere to go and would redeliver
# forever, blocking the CV pipeline behind it (BUG-025).
#
# Same shape as 20-user-events-resources.sh: 14-day retention on the DLQ,
# maxReceiveCount 3 on the primary.
#
# The redrive policy is applied with set-queue-attributes rather than passed to
# create-queue. create-queue is only idempotent when the attributes match an
# existing queue exactly; on any environment where these queues already exist it
# would fail with QueueAlreadyExists. set-queue-attributes is idempotent either
# way, so this script stays safe to re-run.
awslocal sqs create-queue --queue-name "$DOMAIN_QUEUE" >/dev/null
PROCESSOR_QUEUE_URL="$(awslocal sqs create-queue --queue-name "$PROCESSOR_QUEUE" --query QueueUrl --output text)"
awslocal sqs create-queue --queue-name "$PROCESSED_QUEUE" >/dev/null
PROCESSOR_QUEUE_ARN="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${PROCESSOR_QUEUE}"

for q in "$DOMAIN_QUEUE" "$PROCESSOR_QUEUE" "$PROCESSED_QUEUE"; do
  awslocal sqs create-queue \
    --queue-name "${q}-dlq" \
    --attributes "{\"MessageRetentionPeriod\":\"1209600\"}" \
    >/dev/null
  q_url="$(awslocal sqs get-queue-url --queue-name "$q" --query QueueUrl --output text)"
  awslocal sqs set-queue-attributes \
    --queue-url "$q_url" \
    --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${q}-dlq\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"
done

awslocal sqs set-queue-attributes \
  --queue-url "$PROCESSOR_QUEUE_URL" \
  --attributes "{\"Policy\":\"{\\\"Version\\\":\\\"2012-10-17\\\",\\\"Statement\\\":[{\\\"Effect\\\":\\\"Allow\\\",\\\"Principal\\\":{\\\"Service\\\":\\\"s3.amazonaws.com\\\"},\\\"Action\\\":\\\"sqs:SendMessage\\\",\\\"Resource\\\":\\\"${PROCESSOR_QUEUE_ARN}\\\",\\\"Condition\\\":{\\\"ArnLike\\\":{\\\"aws:SourceArn\\\":\\\"arn:aws:s3:::${BUCKET}\\\"}}}]}\"}"

awslocal s3api put-bucket-notification-configuration \
  --bucket "$BUCKET" \
  --notification-configuration "{\"QueueConfigurations\":[{\"QueueArn\":\"${PROCESSOR_QUEUE_ARN}\",\"Events\":[\"s3:ObjectCreated:*\"],\"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"cvs/\"}]}}}]}"
