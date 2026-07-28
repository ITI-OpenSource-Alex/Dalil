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
  description = "Route 53 hosted zone ID for the public domain. Used by future DNS wiring."
  type        = string
  default     = null
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
    notification = {
      port                 = 8087
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    ingestion = {
      port                 = 8088
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
  }
}

variable "ecs_image_tag" {
  description = "Image tag used by ECS task definitions."
  type        = string
  default     = "latest"
}

variable "ecs_desired_counts" {
  description = "Desired task count overrides keyed by service. Defaults to zero for safe initial provisioning."
  type        = map(number)
  default     = {}
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

variable "ecr_cv_processor_repo_url" {
  description = "ECR repository URL for the cv-processor image (without tag)."
  type        = string
  default     = ""
}

variable "ecr_scholarship_matcher_repo_url" {
  description = "ECR repository URL for the scholarship-matcher image (without tag)."
  type        = string
  default     = ""
}

variable "ecr_notification_sender_repo_url" {
  description = "ECR repository URL for the notification-sender image (without tag)."
  type        = string
  default     = ""
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

# NOTE: GitHub provider requires a paid org plan for branch protection.
# Uncomment when the org is upgraded.
# variable "github_token" {
#   description = "GitHub token for the Terraform GitHub provider. Pass via TF_VAR_github_token env var."
#   type        = string
#   sensitive   = true
#   default     = ""
# }

