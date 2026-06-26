variable "environment" {
  description = "Deployment environment name used for naming and tagging."
  type        = string
}

variable "aws_region" {
  description = "AWS region used for the deployment."
  type        = string
  default     = "eu-west-1"
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
