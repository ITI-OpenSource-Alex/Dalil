variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "name_prefix" {
  description = "Environment-qualified resource prefix."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private application subnets used by Fargate tasks."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) == 2
    error_message = "private_subnet_ids must contain exactly two subnets."
  }
}

variable "gateway_security_group_id" {
  description = "Security group assigned to the public gateway task."
  type        = string
}

variable "services_security_group_id" {
  description = "Security group assigned to internal service tasks."
  type        = string
}

variable "task_execution_role_arn" {
  description = "IAM role used by ECS to pull images and initialize containers."
  type        = string
}

variable "task_role_arn" {
  description = "IAM role assumed by running application containers."
  type        = string
}

variable "target_group_arns" {
  description = "ALB target group ARNs keyed by service name."
  type        = map(string)
  default     = {}
}

variable "services" {
  description = "Fargate task and service definitions keyed by service name."
  type = map(object({
    image                             = string
    container_port                    = number
    cpu                               = number
    memory                            = number
    desired_count                     = number
    attach_to_load_balancer           = optional(bool, false)
    health_check_grace_period_seconds = optional(number, 60)
    environment                       = optional(map(string), {})
    secrets                           = optional(map(string), {})
  }))
}

variable "log_retention_days" {
  description = "CloudWatch log retention for task and ECS Exec logs."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Common tags applied to all ECS resources."
  type        = map(string)
  default     = {}
}
