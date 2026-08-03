#!/usr/bin/env bash
set -euo pipefail

project="${PROJECT:-goa}"
region="${AWS_REGION:-eu-west-1}"

command -v aws >/dev/null 2>&1 || { echo "ERROR: aws CLI is required." >&2; exit 1; }

account_id="$(aws sts get-caller-identity --query Account --output text)"
bucket_name="${STATE_BUCKET:-${project}-${account_id}-${region}-terraform-state}"
lock_table_name="${LOCK_TABLE:-${project}-${region}-terraform-locks}"

if ! aws s3api head-bucket --bucket "${bucket_name}" >/dev/null 2>&1; then
  if [[ "${region}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${bucket_name}" --region "${region}"
  else
    aws s3api create-bucket --bucket "${bucket_name}" --region "${region}" \
      --create-bucket-configuration "LocationConstraint=${region}"
  fi
fi

aws s3api put-bucket-versioning --bucket "${bucket_name}" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "${bucket_name}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket "${bucket_name}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-tagging --bucket "${bucket_name}" \
  --tagging "TagSet=[{Key=Project,Value=${project}},{Key=ManagedBy,Value=bootstrap},{Key=Purpose,Value=terraform-state}]"

if ! aws dynamodb describe-table --table-name "${lock_table_name}" --region "${region}" >/dev/null 2>&1; then
  aws dynamodb create-table --table-name "${lock_table_name}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST --region "${region}" \
    --tags Key=Project,Value="${project}" Key=ManagedBy,Value=bootstrap Key=Purpose,Value=terraform-locks
  aws dynamodb wait table-exists --table-name "${lock_table_name}" --region "${region}"
fi

cat > environments/shared.backend.hcl <<BACKEND
bucket               = "${bucket_name}"
key                  = "foundation/terraform.tfstate"
region               = "${region}"
dynamodb_table       = "${lock_table_name}"
encrypt              = true
workspace_key_prefix = "environments"
BACKEND

echo "Remote state is ready in ${bucket_name}."
echo "Run: terraform init -reconfigure -backend-config=environments/shared.backend.hcl"
