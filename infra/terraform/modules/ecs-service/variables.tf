variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "name_prefix" {
  description = "Environment-qualified resource prefix."
  type        = string
}

variable "cluster_id" {
  description = "ECS cluster ID."
  type        = string
}

variable "cluster_name" {
  description = "ECS cluster name used by autoscaling metrics."
  type        = string
}

variable "service_connect_namespace_arn" {
  description = "Cloud Map namespace ARN used by ECS Service Connect."
  type        = string
}

variable "service_name" {
  description = "Logical service name."
  type        = string
}

variable "image_uri" {
  description = "Fully qualified ECR image URI including its tag."
  type        = string
}

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
}

variable "memory" {
  description = "Fargate task memory in MiB."
  type        = number
}

variable "desired_count" {
  description = "Initial desired task count."
  type        = number

  validation {
    condition     = var.desired_count >= 1
    error_message = "GOA ECS services must start with at least one task."
  }
}

variable "container_port" {
  description = "Container and target-group port."
  type        = number
}

variable "environment_variables" {
  description = "Non-sensitive environment variables."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secret environment variables mapped to Secrets Manager valueFrom references."
  type        = map(string)
  default     = {}
}

variable "private_subnet_ids" {
  description = "Private application subnet IDs."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups assigned to the task ENI."
  type        = list(string)
}

variable "task_execution_role_arn" {
  description = "ECS task execution role ARN."
  type        = string
}

variable "task_role_arn" {
  description = "Application task role ARN."
  type        = string
}

variable "target_group_arn" {
  description = "ALB target group ARN."
  type        = string
}

variable "health_check_grace_period_seconds" {
  description = "Grace period before ALB health checks affect deployments."
  type        = number
  default     = 120
}

variable "log_group_name" {
  description = "Existing CloudWatch log group for the service."
  type        = string
}

variable "autoscaling_min_capacity" {
  description = "Minimum ECS task count."
  type        = number
  default     = 1
}

variable "autoscaling_max_capacity" {
  description = "Maximum ECS task count."
  type        = number
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
