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
      port                 = 3000
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
  }
}

variable "task_execution_secret_arns" {
  description = "Secret ARNs the ECS task execution role may read for container startup."
  type        = list(string)
  default     = []
}

variable "task_execution_kms_key_arns" {
  description = "KMS key ARNs the ECS task execution role may decrypt during container startup."
  type        = list(string)
  default     = []
}

variable "task_secret_arns" {
  description = "Secret ARNs the ECS task role may read at runtime."
  type        = list(string)
  default     = []
}

variable "task_sqs_queue_arns" {
  description = "SQS queue ARNs the ECS task role may use at runtime."
  type        = list(string)
  default     = []
}

variable "task_s3_read_object_arns" {
  description = "S3 object ARN patterns ECS application tasks may read, including any externally managed buckets."
  type        = list(string)
  default     = []
}

variable "task_kms_key_arns" {
  description = "KMS key ARNs the ECS task role may use at runtime."
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

  validation {
    condition     = trimspace(var.ecr_cv_processor_repo_url) != ""
    error_message = "ecr_cv_processor_repo_url must not be empty."
  }
}

variable "ecr_scholarship_matcher_repo_url" {
  description = "ECR repository URL for the scholarship-matcher image (without tag)."
  type        = string
}

variable "ecr_notification_sender_repo_url" {
  description = "ECR repository URL for the notification-sender image (without tag)."
  type        = string
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

