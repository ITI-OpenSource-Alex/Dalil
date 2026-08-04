# WARNING:
# Staging and production both default to 10.0.0.0/16 for now.
# If they will run in the same AWS account/region, change one environment to a
# non-overlapping VPC CIDR before applying Terraform.

environment    = "production"
aws_region     = "eu-west-1"
aws_account_id = "114403655381"

vpc_cidr = "10.0.0.0/16"

availability_zones = [
  "eu-west-1a",
  "eu-west-1b",
]

public_subnet_cidrs = [
  "10.0.0.0/24",
  "10.0.1.0/24",
]

private_app_subnet_cidrs = [
  "10.0.10.0/24",
  "10.0.11.0/24",
]

private_data_subnet_cidrs = [
  "10.0.20.0/24",
  "10.0.21.0/24",
]

domain_name               = "swift-sale.me"
hosted_zone_id            = null
enable_public_dns         = true
create_public_hosted_zone = true
alb_certificate_arn       = null

alb_enable_deletion_protection     = true
alb_default_target_group_name      = "gateway"
create_self_signed_alb_certificate = false
enable_cloudfront                  = true
frontend_bucket_name               = "goa-114403655381-production-frontend-assets"
cloudfront_price_class             = "PriceClass_100"
waf_rate_limit                     = 1000
ecs_desired_counts                 = {}
enable_lambda_workers              = false

# GOA-022 (B5/N9): staging owns the account-global GitHub OIDC provider.
# This workspace only creates its own goa-production-deploy role, which
# references the provider by constructed ARN, so tearing down staging can no
# longer destroy production's ability to deploy.
manage_github_oidc_provider = false

task_kms_key_arns = []

ecs_exec_operator_resource_arns    = ["*"]
session_manager_log_retention_days = 90
session_manager_kms_key_id         = ""

tags = {
  Environment = "production"
  Project     = "goa"
  ManagedBy   = "terraform"
  Criticality = "high"
}
