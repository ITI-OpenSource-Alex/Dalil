#!/usr/bin/env bash
#
# Create the eight GOA service databases inside the staging RDS instance.
#
# `terraform apply` provisions the RDS instance but no databases -- see the long
# comment at the top of db_bootstrap.tf. This script runs the one-off Fargate
# task that does it, from inside the VPC, because the instance is deliberately
# not publicly accessible.
#
# Idempotent. The SQL creates each database only WHERE NOT EXISTS, so running
# this twice is safe and is the normal way to pick up a newly added database.
#
# Usage:
#   cd infra/terraform
#   ./db-bootstrap.sh                 # uses the current terraform workspace
#
# Requires: aws cli (authenticated), terraform, jq

set -euo pipefail

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI is required." >&2
  exit 1
fi

# Deliberately no jq dependency -- every value below comes from
# `terraform output -raw` as a plain string. jq is absent from the Git Bash
# environment this project is developed in.

echo "==> Reading Terraform outputs"

cluster="$(terraform output -raw db_bootstrap_cluster_name)"
task_def="$(terraform output -raw db_bootstrap_task_definition_arn)"
log_group="$(terraform output -raw db_bootstrap_log_group)"
subnets="$(terraform output -raw db_bootstrap_subnets)"
security_groups="$(terraform output -raw db_bootstrap_security_groups)"
region="${AWS_REGION:-eu-west-1}"

if [[ -z "${subnets}" || -z "${security_groups}" ]]; then
  echo "ERROR: could not resolve subnets or security groups from Terraform outputs." >&2
  echo "Has 'terraform apply' been run against this workspace?" >&2
  exit 1
fi

echo "    cluster:  ${cluster}"
echo "    region:   ${region}"
echo "    task def: ${task_def}"

echo "==> Running the db-bootstrap task"

task_arn="$(aws ecs run-task \
  --cluster "${cluster}" \
  --task-definition "${task_def}" \
  --launch-type FARGATE \
  --region "${region}" \
  --network-configuration "awsvpcConfiguration={subnets=[${subnets}],securityGroups=[${security_groups}],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' --output text)"

if [[ -z "${task_arn}" || "${task_arn}" == "None" ]]; then
  echo "ERROR: run-task did not return a task ARN." >&2
  exit 1
fi

echo "    task: ${task_arn}"
echo "==> Waiting for it to finish (typically under a minute)"

aws ecs wait tasks-stopped --cluster "${cluster}" --tasks "${task_arn}" --region "${region}"

exit_code="$(aws ecs describe-tasks \
  --cluster "${cluster}" --tasks "${task_arn}" --region "${region}" \
  --query 'tasks[0].containers[0].exitCode' --output text)"

stopped_reason="$(aws ecs describe-tasks \
  --cluster "${cluster}" --tasks "${task_arn}" --region "${region}" \
  --query 'tasks[0].stoppedReason' --output text)"

echo "==> Task output"

# The log stream may take a moment to appear after the task stops.
task_id="${task_arn##*/}"
stream="db-bootstrap/db-bootstrap/${task_id}"
for _ in 1 2 3 4 5 6; do
  if aws logs get-log-events \
      --log-group-name "${log_group}" \
      --log-stream-name "${stream}" \
      --region "${region}" \
      --query 'events[].message' --output text 2>/dev/null | grep -q .; then
    break
  fi
  sleep 5
done

aws logs get-log-events \
  --log-group-name "${log_group}" \
  --log-stream-name "${stream}" \
  --region "${region}" \
  --query 'events[].message' --output text 2>/dev/null \
  | tr '\t' '\n' | sed 's/^/    /' || echo "    (no log events retrieved)"

echo
if [[ "${exit_code}" != "0" ]]; then
  echo "FAILED: db-bootstrap exited ${exit_code} (${stopped_reason})" >&2
  echo "Read the full logs with:" >&2
  echo "  aws logs tail ${log_group} --since 15m --region ${region}" >&2
  exit 1
fi

echo "OK: db-bootstrap completed. The database list above is the live contents of the instance."
echo "Paste it into the GOA-021 PR as evidence for the '8 service databases' criterion."
