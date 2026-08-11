variable "environment" {
  description = "Deployment environment name used for naming and tagging."
  type        = string
}

variable "aws_region" {
  description = "AWS region used for the deployment."
  type        = string
  default     = "eu-west-1"
}

variable "aws_offline_mode" {
  description = "Use mock AWS credentials only for local terraform plan validation. Never enable for apply."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "Primary CIDR block for the VPC."
  type        = string
}

variable "availability_zones" {
  description = "Exactly two availability zones used to spread the network across the region."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "availability_zones must contain exactly two AZs."
  }
}

variable "public_subnet_cidrs" {
  description = "Two CIDR blocks for public subnets that host the ALB and NAT gateways."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "public_subnet_cidrs must contain exactly two CIDR blocks."
  }
}

variable "private_app_subnet_cidrs" {
  description = "Two CIDR blocks for private application subnets used by ECS/services."
  type        = list(string)

  validation {
    condition     = length(var.private_app_subnet_cidrs) == 2
    error_message = "private_app_subnet_cidrs must contain exactly two CIDR blocks."
  }
}

variable "private_data_subnet_cidrs" {
  description = "Two CIDR blocks for private data subnets used by databases and caches."
  type        = list(string)

  validation {
    condition     = length(var.private_data_subnet_cidrs) == 2
    error_message = "private_data_subnet_cidrs must contain exactly two CIDR blocks."
  }
}

variable "alb_certificate_arn" {
  description = "ACM certificate ARN used by the public ALB HTTPS listener."
  type        = string
  default     = null
  nullable    = true
}

variable "create_self_signed_alb_certificate" {
  description = "Create a self-signed ACM certificate for non-production validation. Must be false in production."
  type        = bool
  default     = false

  validation {
    condition     = !(var.environment == "production" && var.create_self_signed_alb_certificate)
    error_message = "Production must use a trusted ACM certificate."
  }
}

variable "enable_cloudfront" {
  description = "Create a CloudFront distribution in front of the ALB."
  type        = bool
  default     = false
}

variable "cloudfront_price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_100"
}

variable "domain_name" {
  description = "Primary DNS name planned for the public application entry point."
  type        = string
  default     = null
}

variable "hosted_zone_id" {
  description = "Existing Route 53 hosted zone ID. Leave null when Terraform creates the production zone."
  type        = string
  default     = null
  nullable    = true
}

variable "enable_public_dns" {
  description = "Provision public Route 53, ACM, WAF, CloudFront, and DNS resources."
  type        = bool
  default     = false
}

variable "create_public_hosted_zone" {
  description = "Create the public Route 53 hosted zone. Set false and provide hosted_zone_id to use an existing zone."
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_public_dns || var.create_public_hosted_zone || var.hosted_zone_id != null
    error_message = "Public DNS requires create_public_hosted_zone=true or an existing hosted_zone_id."
  }
}

variable "frontend_bucket_name" {
  description = "Optional globally unique name for the private frontend asset bucket."
  type        = string
  default     = null
  nullable    = true
}

variable "waf_rate_limit" {
  description = "Maximum requests per IP during WAF's five-minute evaluation window."
  type        = number
  default     = 1000
}

variable "alb_enable_deletion_protection" {
  description = "Whether deletion protection is enabled on the public ALB."
  type        = bool
  default     = false
}

variable "alb_default_target_group_name" {
  description = "Target group key used by the ALB HTTPS listener default action."
  type        = string
  default     = "gateway"
}

variable "alb_target_groups" {
  description = "ALB target groups for the gateway and internal services."
  type = map(object({
    port                 = number
    protocol             = string
    health_check_path    = string
    deregistration_delay = number
  }))
  default = {
    gateway = {
      port                 = 8080
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    user = {
      port                 = 8081
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    orchestration = {
      port                 = 8083
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
    rag = {
      port                 = 8084
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    writing = {
      port                 = 8000
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
}

variable "ecs_image_tag" {
  description = "Placeholder image tag for the task definition Terraform creates. CI owns the real tag (the commit SHA) from the first deploy onward."
  type        = string
  default     = "bootstrap"

  validation {
    condition     = var.ecs_image_tag != "latest"
    error_message = "ecs_image_tag must not be 'latest': ECR repositories are IMMUTABLE (GOA-022 N7), so a floating tag cannot be re-pushed and would pin every service to one set of bytes forever."
  }
}

# GOA-030 — RAG's embedding endpoint.
#
# This was missing entirely, and its absence is not cosmetic: it is the reason a
# deployed environment could not answer a single question.
#
# services/rag/app/core/config.py defaults embedding_base_url to
# "http://host.docker.internal:11434/v1" -- an Ollama server on the DEVELOPER'S
# HOST, deliberately not a compose service and certainly not reachable from a
# Fargate task in a private subnet. Terraform set no override, so a deployed RAG
# falls back to that address and every /query and /match fails at the embedding
# call.
#
# It fails quietly, too. The repo README already documents the local version of
# this trap: Ollama answers 404 only when the first query arrives, POST /query
# turns that into a 500, orchestration falls back, and the chat shows a generic
# error with the real cause visible only in the RAG container's logs.
#
# There is deliberately no working default. Choosing one would mean choosing an
# embedding provider on the project's behalf, and the choice is load-bearing:
# the dimension must match the pgvector column or every insert and query fails.
variable "rag_embedding_base_url" {
  description = "OpenAI-compatible embeddings endpoint for the RAG service. Must be set before RAG can serve traffic."
  type        = string
  default     = ""
}

variable "rag_embedding_model" {
  description = "Embedding model name. Must produce vectors of rag_embedding_dimensions."
  type        = string
  default     = "nomic-embed-text"
}

variable "rag_embedding_dimensions" {
  description = "Embedding width. MUST match the pgvector column (currently vector(768)); a mismatch fails at insert/query time, not at startup."
  type        = number
  default     = 768
}

variable "ecs_desired_counts" {
  description = "Desired task count overrides keyed by ECS service. Each deployed service defaults to one."
  type        = map(number)
  default     = {}

  validation {
    condition     = alltrue([for count in values(var.ecs_desired_counts) : count >= 0])
    error_message = "ECS desired counts cannot be negative."
  }
}

variable "weekly_program_ingestion_schedule" {
  description = "EventBridge schedule for the Tier 1 MastersPortal catalog sweep."
  type        = string
  default     = "cron(0 2 ? * SUN *)"
}

variable "monthly_visa_ingestion_schedule" {
  description = "EventBridge schedule for source-hash visa verification."
  type        = string
  default     = "cron(0 3 1 * ? *)"
}

variable "enable_lambda_workers" {
  description = "Create image-based Lambda workers after their ECR images have been published."
  type        = bool
  default     = false
}

variable "task_kms_key_arns" {
  description = "Optional KMS keys used by per-service ECS roles."
  type        = list(string)
  default     = []
}

variable "ecs_exec_operator_resource_arns" {
  description = "ECS cluster/task/service ARNs operators may use with ECS Exec. Replace the default once ECS resources exist."
  type        = list(string)
  default     = ["*"]
}

variable "session_manager_log_retention_days" {
  description = "Retention period in days for Session Manager CloudWatch logs."
  type        = number
  default     = 30
}

variable "session_manager_kms_key_id" {
  description = "Optional KMS key ID or ARN used to encrypt Session Manager logs."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "aws_account_id" {
  description = "AWS account ID, used for S3 bucket notification source_account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "image_tag" {
  description = "Container image tag to deploy for all Lambda workers (CI passes the git SHA)."
  type        = string
  default     = "latest"
}

variable "lambda_secret_arns" {
  description = "Secret ARNs Lambda workers may read. Empty until modules/secrets exists."
  type        = list(string)
  default     = []
}

variable "sqs_notification_queue_arn" {

  type    = string
  default = null
}

variable "sqs_notification_queue_url" {
  description = "URL of the SQS queue notification-sender consumes. Null until modules/sqs exists."
  type        = string
  default     = null
}

# -----------------------------------------------------------------------------
# GOA-074: GitHub & OIDC Configuration
# -----------------------------------------------------------------------------

variable "github_org" {
  description = "GitHub organization or username that owns the repository."
  type        = string
  default     = "ITI-OpenSource-Alex"
}

variable "github_repo" {
  description = "GitHub repository name (without the org prefix)."
  type        = string
  default     = "GOA"
}

variable "manage_github_oidc_provider" {
  description = <<-EOT
    Whether this workspace creates the account-global GitHub OIDC identity
    provider. Exactly one workspace in the account may set this to true
    (staging, by default) -- IAM OIDC providers are global, so a second apply
    would fail with EntityAlreadyExists. Set false in production.tfvars.
  EOT
  type        = bool
  default     = true
}

# NOTE: GitHub provider requires a paid org plan for branch protection.
# Uncomment when the org is upgraded.
# variable "github_token" {
#   description = "GitHub token for the Terraform GitHub provider. Pass via TF_VAR_github_token env var."
#   type        = string
#   sensitive   = true
#   default     = ""
# }


# GOA-046 cost monitoring. Defaults to off: the AWS Budgets and Cost Explorer
# resources in cost_monitoring.tf cannot be applied from this account, which
# carries an explicit deny on billing:* and ce:*. See that file's header.
variable "enable_cost_monitoring" {
  description = "Create the AWS Budgets alert and weekly Cost Explorer report Lambda."
  type        = bool
  default     = false
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget in USD, alerted at 80% and 100% of actual spend."
  type        = number
  default     = 150
}

variable "cost_report_sender_address" {
  description = "SES-verified sender address for the weekly cost report."
  type        = string
  default     = ""
}

variable "cost_report_recipients" {
  description = "Recipients of the budget alerts and the weekly cost report."
  type        = list(string)
  default     = []
}
