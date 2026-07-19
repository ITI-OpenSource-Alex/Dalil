#!/bin/sh
set -eu

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"
BUCKET="goa-writing-files"
DOMAIN_QUEUE="goa-cv-uploaded"
PROCESSOR_QUEUE="goa-cv-processing"
PROCESSED_QUEUE="goa-cv-processed"

awslocal s3api create-bucket --bucket "$BUCKET" >/dev/null 2>&1 || true
awslocal sqs create-queue --queue-name "$DOMAIN_QUEUE" >/dev/null
PROCESSOR_QUEUE_URL="$(awslocal sqs create-queue --queue-name "$PROCESSOR_QUEUE" --query QueueUrl --output text)"
awslocal sqs create-queue --queue-name "$PROCESSED_QUEUE" >/dev/null
PROCESSOR_QUEUE_ARN="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${PROCESSOR_QUEUE}"

awslocal sqs set-queue-attributes \
  --queue-url "$PROCESSOR_QUEUE_URL" \
  --attributes "{\"Policy\":\"{\\\"Version\\\":\\\"2012-10-17\\\",\\\"Statement\\\":[{\\\"Effect\\\":\\\"Allow\\\",\\\"Principal\\\":{\\\"Service\\\":\\\"s3.amazonaws.com\\\"},\\\"Action\\\":\\\"sqs:SendMessage\\\",\\\"Resource\\\":\\\"${PROCESSOR_QUEUE_ARN}\\\",\\\"Condition\\\":{\\\"ArnLike\\\":{\\\"aws:SourceArn\\\":\\\"arn:aws:s3:::${BUCKET}\\\"}}}]}\"}"

awslocal s3api put-bucket-notification-configuration \
  --bucket "$BUCKET" \
  --notification-configuration "{\"QueueConfigurations\":[{\"QueueArn\":\"${PROCESSOR_QUEUE_ARN}\",\"Events\":[\"s3:ObjectCreated:*\"],\"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"cvs/\"}]}}}]}"
