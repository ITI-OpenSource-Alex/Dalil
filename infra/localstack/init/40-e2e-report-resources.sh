#!/bin/sh
set -eu

# GOA-030 E2E evidence bucket.
#
# The ticket asks for the run summary at s3://.../tests/e2e/{timestamp}/summary.json
# plus screenshots and Playwright traces for any failing step. There is no AWS
# account on this project (GOA-021 never got credentials), so "S3" here is
# LocalStack -- the same endpoint, credentials and region every other service in
# this stack already uses for SQS, SES and the writing/exam buckets.
#
# Keeping the object layout identical to the ticket's means the only thing that
# changes on a real account is the endpoint URL.

BUCKET="goa-e2e-reports"

awslocal s3api create-bucket --bucket "$BUCKET" >/dev/null 2>&1 || true

# Runs accumulate one prefix per timestamp and nothing ever deletes them, so a
# developer who runs the suite daily would otherwise grow this without bound.
# 30 days is longer than any debugging session and shorter than forever.
awslocal s3api put-bucket-lifecycle-configuration \
  --bucket "$BUCKET" \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "expire-e2e-runs",
        "Status": "Enabled",
        "Filter": {"Prefix": "tests/e2e/"},
        "Expiration": {"Days": 30}
      }
    ]
  }' >/dev/null 2>&1 || true

echo "GOA-030: s3://${BUCKET}/tests/e2e/ ready"
