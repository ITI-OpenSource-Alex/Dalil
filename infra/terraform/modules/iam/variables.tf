variable "environment" {
  description = "Deployment environment name used for tagging and naming."
  type        = string
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

variable "session_manager_run_as_enabled" {
  description = "Whether Session Manager sessions should run as a configured operating system user."
  type        = bool
  default     = false
}

variable "session_manager_run_as_default_user" {
  description = "Default operating system user for Session Manager run-as sessions."
  type        = string
  default     = "ssm-user"
}

variable "session_manager_log_group_name" {
  description = "CloudWatch log group name for Session Manager logs. Defaults to an environment-specific name."
  type        = string
  default     = null
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

variable "session_manager_s3_bucket_name" {
  description = "Optional S3 bucket name for Session Manager log delivery."
  type        = string
  default     = ""
}

variable "session_manager_s3_key_prefix" {
  description = "Optional S3 key prefix for Session Manager log delivery."
  type        = string
  default     = "session-manager"
}

variable "session_manager_idle_timeout_minutes" {
  description = "Idle timeout, in minutes, for Session Manager sessions."
  type        = number
  default     = 20
}

variable "session_manager_max_duration_minutes" {
  description = "Maximum duration, in minutes, for Session Manager sessions."
  type        = number
  default     = 60
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default     = {}
}
