#!/bin/sh
set -eu

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"
TOPIC="user-events"

create_queue_with_dlq() {
  queue="$1"
  dlq="${queue}-dlq"

  awslocal sqs create-queue \
    --queue-name "$dlq" \
    --attributes "{\"MessageRetentionPeriod\":\"1209600\"}" \
    >/dev/null

  dlq_arn="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${dlq}"

  awslocal sqs create-queue \
    --queue-name "$queue" \
    --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
    >/dev/null
}

topic_arn="$(awslocal sns create-topic --name "$TOPIC" --query TopicArn --output text)"

for queue in \
  user-events-rag \
  user-events-orchestration \
  user-events-exam \
  user-events-speaking \
  user-events-writing \
  user-events-notification
do
  create_queue_with_dlq "$queue"
done

for queue in \
  user-events-rag \
  user-events-orchestration \
  user-events-exam \
  user-events-speaking \
  user-events-writing \
  user-events-notification
do
  queue_arn="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:${queue}"
  queue_url="$(awslocal sqs get-queue-url --queue-name "$queue" --query QueueUrl --output text)"
  awslocal sqs set-queue-attributes \
    --queue-url "$queue_url" \
    --attributes "{\"Policy\":\"{\\\"Version\\\":\\\"2012-10-17\\\",\\\"Statement\\\":[{\\\"Effect\\\":\\\"Allow\\\",\\\"Principal\\\":{\\\"Service\\\":\\\"sns.amazonaws.com\\\"},\\\"Action\\\":\\\"sqs:SendMessage\\\",\\\"Resource\\\":\\\"${queue_arn}\\\",\\\"Condition\\\":{\\\"ArnEquals\\\":{\\\"aws:SourceArn\\\":\\\"${topic_arn}\\\"}}}]}\"}"

  awslocal sns subscribe \
    --topic-arn "$topic_arn" \
    --protocol sqs \
    --notification-endpoint "$queue_arn" \
    --attributes RawMessageDelivery=true \
    >/dev/null
done
