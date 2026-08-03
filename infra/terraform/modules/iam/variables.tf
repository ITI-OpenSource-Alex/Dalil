variable "environment" {
  description = "Deployment environment name used for tagging and naming."
  type        = string
}

variable "ecs_service_permissions" {
  description = "Least-privilege execution and runtime permissions keyed by ECS service."
  type = map(object({
    execution_secret_arns = set(string)
    task_secret_arns      = set(string)
    sqs_queue_arns        = set(string)
    sns_topic_arns        = set(string)
    s3_read_object_arns   = set(string)
    s3_write_object_arns  = set(string)
    kms_key_arns          = set(string)
  }))
}

variable "ecs_exec_operator_resource_arns" {
  description = "ECS cluster/task/service ARNs operators may use with ECS Exec."
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
  description = "CloudWatch log group name for Session Manager logs."
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

variable "lambda_secret_arns" {
  description = "Secret ARNs Lambda workers may read at runtime."
  type        = list(string)
  default     = []
}

variable "lambda_kms_key_arns" {
  description = "KMS key ARNs Lambda workers may use at runtime."
  type        = list(string)
  default     = []
}

variable "lambda_sqs_queue_arns" {
  description = "SQS queue ARNs Lambda workers may use at runtime."
  type        = list(string)
  default     = []
}

variable "lambda_s3_bucket_arns" {
  description = "S3 bucket ARNs Lambda workers may read objects from."
  type        = list(string)
  default     = []
}
