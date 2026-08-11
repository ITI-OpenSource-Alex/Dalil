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
enable_public_dns                  = false
create_public_hosted_zone          = false
alb_certificate_arn                = null
create_self_signed_alb_certificate = true
enable_cloudfront                  = false

alb_enable_deletion_protection = false
alb_default_target_group_name  = "gateway"

# GOA-030: only the services the ALB actually routes to get a target group.
#
# The default defines seven, but main.tf wires listener rules for exactly three
# -- gateway (the listener default), speaking (/api/speaking/ws) and exam
# (/api/exam/*). ECS refuses to create a service whose target group has no
# associated load balancer, so user, orchestration, rag and writing failed with
# "The target group ... does not have an associated load balancer" and four of
# the ten services never came up.
#
# Removing them is the correct fix rather than adding four more listener rules:
# those services are internal. The Gateway reaches them over Service Connect
# (RAG_SERVICE_URL = http://goa-staging-rag:8084 and friends in locals.tf), and
# putting them behind the public ALB would expose services that deliberately sit
# behind the Gateway's JWT, rate limiting and correlation IDs.
alb_target_groups = {
  gateway = {
    port                 = 8080
    protocol             = "HTTP"
    health_check_path    = "/health"
    deregistration_delay = 30
  }
  speaking = {
    port                 = 8082
    protocol             = "HTTP"
    health_check_path    = "/health"
    deregistration_delay = 30
  }
  exam = {
    port                 = 8085
    protocol             = "HTTP"
    health_check_path    = "/health"
    deregistration_delay = 30
  }
}

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
  # GOA-030: the two sidecars a deployed environment cannot serve traffic
  # without. speech is Speaking's STT; embeddings is the Ollama server RAG
  # embeds every query through.
  speech     = 1
  embeddings = 1
}

# GOA-030: images pushed by infra/build-and-push.sh. NOT "latest" -- ECR
# repositories are immutable, so a tag is written once; bump this to redeploy.
# goa030-1 was pushed by Buildx with default attestations, so the tag resolved to
# a 1.5 KB in-toto manifest and Fargate refused it with "mismatched image rootfs
# and manifest layers". goa030-2 is the same source built with
# --provenance=false --sbom=false. ECR tags are immutable, hence a new tag rather
# than a re-push.
# goa030-3 additionally carries the RDS CA bundle in the user image; without it
# the user service crash-loops on SELF_SIGNED_CERT_IN_CHAIN and the Gateway
# answers "no healthy upstream" for every auth route.
ecs_image_tag = "goa030-3"
# GOA-030: the three image-based Lambda workers reference the :latest tag, which
# this project's immutable-ECR pipeline never produces -- so every apply failed
# with "Source image ...:latest does not exist". None of them sit on a path the
# load test exercises (CV processing, scholarship matching and notification
# sending are asynchronous side flows), so staging runs without them rather than
# blocking the environment on three more images.
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

# GOA-030: both of these are ACCOUNT-GLOBAL and already exist in 114403655381,
# left behind by an earlier apply whose destroy did not remove IAM. Creating
# them again fails with EntityAlreadyExists / DocumentAlreadyExists, and
# importing them into THIS workspace would mean `terraform destroy` on staging
# deletes the account's GitHub Actions OIDC provider and its Session Manager
# document. Staging therefore uses them without owning them.
manage_github_oidc_provider        = false
manage_session_manager_preferences = false
