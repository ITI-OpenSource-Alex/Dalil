#!/usr/bin/env bash
#
# GOA-071 smoke test — run after `terraform apply` against a real (staging)
# account. Checks each "Definition of done" line from the ticket.
#
# Requires: aws cli (authenticated), terraform, jq, bc
#
# Usage:
#   ./test/goa-071-smoke-test.sh staging
#
# to run cd infra/terraform
# terraform apply -var-file=environments/staging.tfvars
# chmod +x test/goa-071-smoke-test.sh
# ./test/goa-071-smoke-test.sh staging

set -euo pipefail

ENVIRONMENT="${1:-staging}"
WRITING_FILES_BUCKET="goa-writing-files-${ENVIRONMENT}"
CV_PROCESSOR_FUNCTION="goa-cv-processor-${ENVIRONMENT}"
WEEKLY_INGESTION_RULE="goa-weekly-ingestion-${ENVIRONMENT}"
DAILY_MATCH_RULE="goa-daily-scholarship-match-${ENVIRONMENT}"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

# -----------------------------------------------------------------------
# 1. EventBridge rules visible with correct cron expressions
# -----------------------------------------------------------------------
echo "== 1. EventBridge rules =="

check_rule_cron() {
  local rule_name="$1"
  local expected_cron="$2"
  local actual_cron

  actual_cron=$(aws events describe-rule --name "$rule_name" \
    --query 'ScheduleExpression' --output text 2>/dev/null || echo "MISSING")

  if [[ "$actual_cron" == "$expected_cron" ]]; then
    pass "$rule_name has schedule $actual_cron"
  else
    fail "$rule_name expected [$expected_cron] got [$actual_cron]"
  fi
}

check_rule_cron "$WEEKLY_INGESTION_RULE" "cron(0 2 ? * SUN *)"
check_rule_cron "$DAILY_MATCH_RULE" "cron(0 8 * * ? *)"

# -----------------------------------------------------------------------
# 2. S3 -> cv-processor trigger — verify cvs/ fires, essays/ does NOT
#
# NOTE: the ticket's Definition of Done says to test against `essays/`.
# That prefix is stale (see GOA-087) — the acceptance criteria and the
# actual Terraform implement `cvs/`. This script tests BOTH: that cvs/
# correctly fires the Lambda, and that essays/ correctly does NOT, which
# is the real proof the implementation matches the acceptance criteria.
# -----------------------------------------------------------------------
echo "== 2. S3 trigger (cvs/ prefix) =="

TEST_FILE="$(mktemp)"
echo "smoke test $(date -u +%Y%m%dT%H%M%SZ)" > "$TEST_FILE"

get_invocation_count() {
  local function_name="$1"
  local since_epoch_ms="$2"
  aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value="$function_name" \
    --start-time "$(date -u -d "@$((since_epoch_ms / 1000))" +%Y-%m-%dT%H:%M:%S)" \
    --end-time "$(date -u +%Y-%m-%dT%H:%M:%S)" \
    --period 60 \
    --statistics Sum \
    --query 'sum(Datapoints[].Sum)' \
    --output text 2>/dev/null || echo "0"
}

test_prefix_trigger() {
  local prefix="$1"
  local should_fire="$2"   # "yes" or "no"
  local key="${prefix}smoketest-$(date +%s).txt"
  local before_ms
  before_ms=$(($(date +%s%N) / 1000000))

  aws s3 cp "$TEST_FILE" "s3://${WRITING_FILES_BUCKET}/${key}" >/dev/null

  echo "  uploaded s3://${WRITING_FILES_BUCKET}/${key} — waiting 35s for invocation..."
  sleep 35

  local invocations
  invocations=$(get_invocation_count "$CV_PROCESSOR_FUNCTION" "$before_ms")
  invocations=${invocations:-0}
  [[ "$invocations" == "None" ]] && invocations=0

  if [[ "$should_fire" == "yes" ]]; then
    if (( $(echo "$invocations > 0" | bc -l 2>/dev/null || echo 0) )); then
      pass "upload to ${prefix} triggered cv-processor ($invocations invocation(s))"
    else
      fail "upload to ${prefix} did NOT trigger cv-processor within 35s"
    fi
  else
    if (( $(echo "$invocations > 0" | bc -l 2>/dev/null || echo 0) )); then
      fail "upload to ${prefix} triggered cv-processor — should NOT have (essays are never extracted, see GOA-087)"
    else
      pass "upload to ${prefix} correctly did NOT trigger cv-processor"
    fi
  fi

  aws s3 rm "s3://${WRITING_FILES_BUCKET}/${key}" >/dev/null 2>&1 || true
}

test_prefix_trigger "cvs/" "yes"
test_prefix_trigger "essays/" "no"

rm -f "$TEST_FILE"

# -----------------------------------------------------------------------
# 3. S3 bucket policy confirms public access is blocked (live check)
# -----------------------------------------------------------------------
echo "== 3. Public access block (live buckets) =="

BUCKETS=(
  "goa-writing-files-${ENVIRONMENT}"
  "goa-exam-audio-${ENVIRONMENT}"
  "goa-ingestion-reports-${ENVIRONMENT}"
  "goa-eval-reports-${ENVIRONMENT}"
)

for bucket in "${BUCKETS[@]}"; do
  config=$(aws s3api get-public-access-block --bucket "$bucket" \
    --query 'PublicAccessBlockConfiguration' --output json 2>/dev/null || echo "{}")

  block_acls=$(echo "$config" | jq -r '.BlockPublicAcls // false')
  block_policy=$(echo "$config" | jq -r '.BlockPublicPolicy // false')
  ignore_acls=$(echo "$config" | jq -r '.IgnorePublicAcls // false')
  restrict_buckets=$(echo "$config" | jq -r '.RestrictPublicBuckets // false')

  if [[ "$block_acls" == "true" && "$block_policy" == "true" && "$ignore_acls" == "true" && "$restrict_buckets" == "true" ]]; then
    pass "$bucket has all four public-access-block flags set"
  else
    fail "$bucket public access block incomplete: $config"
  fi
done

# -----------------------------------------------------------------------
# 5. block_public_acls = true in Terraform state
# -----------------------------------------------------------------------
echo "== 5. block_public_acls in Terraform state =="

STATE_JSON=$(terraform show -json 2>/dev/null || echo '{}')

pab_resources=$(echo "$STATE_JSON" | jq -r '
  .values.root_module.child_modules[]?
  | .resources[]?
  | select(.type == "aws_s3_bucket_public_access_block")
  | "\(.address)=\(.values.block_public_acls)"
')

if [[ -z "$pab_resources" ]]; then
  fail "no aws_s3_bucket_public_access_block resources found in state — did you run terraform apply?"
else
  while IFS= read -r line; do
    addr="${line%%=*}"
    value="${line##*=}"
    if [[ "$value" == "true" ]]; then
      pass "$addr: block_public_acls = true"
    else
      fail "$addr: block_public_acls = $value"
    fi
  done <<< "$pab_resources"
fi

# -----------------------------------------------------------------------
echo ""
echo "== Summary =="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

if (( FAIL > 0 )); then
  exit 1
fi