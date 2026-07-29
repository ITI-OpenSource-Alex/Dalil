# WARNING:
# Staging and production both default to 10.0.0.0/16 for now.
# If they will run in the same AWS account/region, change one environment to a
# non-overlapping VPC CIDR before applying Terraform.

environment    = "staging"
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

domain_name                        = "staging.goa.internal"
hosted_zone_id                     = null
alb_certificate_arn                = null
create_self_signed_alb_certificate = true
enable_cloudfront                  = false

alb_enable_deletion_protection = false
alb_default_target_group_name  = "gateway"

# GOA-022 (N7): ecs_image_tag is deliberately NOT set here. ECR is IMMUTABLE,
# so "latest" cannot be re-pushed; the variable defaults to the "bootstrap"
# placeholder and CI owns the real tag (the commit SHA) from the first deploy
# onward. See variables.tf.
ecs_desired_counts = {
  gateway       = 1
  user          = 1
  orchestration = 1
  speaking      = 1
  writing       = 1
  rag           = 1
  exam          = 1
  notification  = 0
  ingestion     = 0
}
enable_lambda_workers            = false
enable_rds_proxy                 = false # RDS Proxy is unavailable on AWS free-plan accounts.
rds_backup_retention_days        = 1     # AWS free-plan maximum; production remains 7 days.
rds_performance_insights_enabled = false

task_kms_key_arns = []

ecs_exec_operator_resource_arns    = ["*"]
session_manager_log_retention_days = 30
session_manager_kms_key_id         = ""

tags = {
  Environment = "staging"
  Project     = "goa"
  ManagedBy   = "terraform"
}
