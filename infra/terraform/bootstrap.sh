#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage:
  ./bootstrap.sh <environment> [--region eu-west-1] [--project goa] [--bucket-name name] [--lock-table-name name]

Examples:
  ./bootstrap.sh staging
  ./bootstrap.sh production --region eu-west-1

This creates the one-time remote state infrastructure for an environment:
  - S3 bucket for Terraform state
  - DynamoDB table for state locking

After it succeeds, copy the printed backend block into backend.tf and run:
  terraform init -migrate-state
USAGE
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: '$1' is required but was not found in PATH." >&2
    exit 1
  fi
}

environment="${1:-}"

if [[ -z "${environment}" || "${environment}" == "-h" || "${environment}" == "--help" ]]; then
  usage
  exit 0
fi

shift || true

project="goa"
region="eu-west-1"
bucket_name=""
lock_table_name=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      project="${2:-}"
      shift 2
      ;;
    --region)
      region="${2:-}"
      shift 2
      ;;
    --bucket-name)
      bucket_name="${2:-}"
      shift 2
      ;;
    --lock-table-name)
      lock_table_name="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

case "${environment}" in
  staging|production)
    ;;
  *)
    echo "ERROR: environment must be 'staging' or 'production'." >&2
    exit 1
    ;;
esac

if [[ -z "${project}" || -z "${region}" ]]; then
  echo "ERROR: project and region must not be empty." >&2
  exit 1
fi

require_command aws

account_id="$(aws sts get-caller-identity --query Account --output text)"
bucket_name="${bucket_name:-${project}-${environment}-${account_id}-${region}-terraform-state}"
lock_table_name="${lock_table_name:-${project}-${environment}-${region}-terraform-locks}"
state_key="foundation/terraform.tfstate"

echo "Bootstrapping Terraform remote state for ${project}/${environment} in ${region}."
echo "AWS account: ${account_id}"
echo "S3 bucket: ${bucket_name}"
echo "DynamoDB table: ${lock_table_name}"

if aws s3api head-bucket --bucket "${bucket_name}" >/dev/null 2>&1; then
  echo "S3 bucket already exists: ${bucket_name}"
else
  echo "Creating S3 bucket: ${bucket_name}"
  if [[ "${region}" == "us-east-1" ]]; then
    aws s3api create-bucket \
      --bucket "${bucket_name}" \
      --region "${region}"
  else
    aws s3api create-bucket \
      --bucket "${bucket_name}" \
      --region "${region}" \
      --create-bucket-configuration "LocationConstraint=${region}"
  fi
fi

echo "Enabling S3 bucket versioning."
aws s3api put-bucket-versioning \
  --bucket "${bucket_name}" \
  --versioning-configuration Status=Enabled

echo "Enabling default S3 server-side encryption."
aws s3api put-bucket-encryption \
  --bucket "${bucket_name}" \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        }
      }
    ]
  }'

echo "Blocking public access to the state bucket."
aws s3api put-public-access-block \
  --bucket "${bucket_name}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "Tagging S3 state bucket."
aws s3api put-bucket-tagging \
  --bucket "${bucket_name}" \
  --tagging "TagSet=[{Key=Project,Value=${project}},{Key=Environment,Value=${environment}},{Key=ManagedBy,Value=terraform},{Key=Purpose,Value=terraform-state}]"

if aws dynamodb describe-table --table-name "${lock_table_name}" --region "${region}" >/dev/null 2>&1; then
  echo "DynamoDB lock table already exists: ${lock_table_name}"
else
  echo "Creating DynamoDB lock table: ${lock_table_name}"
  aws dynamodb create-table \
    --table-name "${lock_table_name}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --tags Key=Project,Value="${project}" Key=Environment,Value="${environment}" Key=ManagedBy,Value=terraform Key=Purpose,Value=terraform-locks \
    --region "${region}"

  echo "Waiting for DynamoDB lock table to become active."
  aws dynamodb wait table-exists \
    --table-name "${lock_table_name}" \
    --region "${region}"
fi

cat <<BACKEND

Remote state infrastructure is ready.

Use this backend block in backend.tf when you are ready to migrate from local state:

terraform {
  backend "s3" {
    bucket         = "${bucket_name}"
    key            = "${state_key}"
    region         = "${region}"
    dynamodb_table = "${lock_table_name}"
    encrypt        = true
  }
}

Then run:
  terraform init -migrate-state
BACKEND
