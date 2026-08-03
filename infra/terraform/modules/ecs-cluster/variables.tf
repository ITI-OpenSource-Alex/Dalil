variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "name_prefix" {
  description = "Environment-qualified resource prefix."
  type        = string
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
