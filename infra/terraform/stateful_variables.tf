variable "project_name" {
  description = "Short project name used for resource naming."
  type        = string
  default     = "goa"
}

variable "alert_email_addresses" {
  description = "Email addresses subscribed to the GOA alerts SNS topic."
  type        = list(string)
  default     = []
}

variable "ecs_cluster_name" {
  description = "ECS cluster name used for Container Insights alarms."
  type        = string
  default     = ""
}

variable "goa069_ecs_service_names" {
  description = "Optional ECS service names keyed by GOA service."
  type        = map(string)
  default     = {}
}

variable "service_secret_values" {
  description = "Optional service secret values."
  type        = map(map(string))
  default     = {}
  sensitive   = true
}

variable "secrets_kms_key_id" {
  description = "Optional KMS key ID or ARN for Secrets Manager encryption."
  type        = string
  default     = null
}

variable "rds_allocated_storage_gb" {
  description = "Initial RDS allocated storage in GB."
  type        = number
  default     = 20
}

variable "rds_max_allocated_storage_gb" {
  description = "Maximum RDS autoscaled storage in GB."
  type        = number
  default     = 100
}

variable "rds_engine_version" {
  description = "PostgreSQL engine version."
  type        = string
  default     = "16.3"
}

variable "redis_num_cache_clusters" {
  description = "Number of Redis cache clusters in the replication group."
  type        = number
  default     = 1
}

variable "redis_transit_encryption_enabled" {
  description = "Whether Redis traffic uses in-transit encryption."
  type        = bool
  default     = false
}

variable "redis_auth_token" {
  description = "Optional Redis auth token; requires transit encryption."
  type        = string
  default     = null
  sensitive   = true
}

variable "speaking_p95_latency_threshold_ms" {
  description = "Speaking P95 latency alarm threshold in milliseconds."
  type        = number
  default     = 2000
}

variable "service_error_rate_threshold" {
  description = "Service error-rate alarm threshold."
  type        = number
  default     = 5
}

variable "dlq_visible_messages_threshold" {
  description = "DLQ visible-message alarm threshold."
  type        = number
  default     = 1
}

variable "ecs_running_task_minimum" {
  description = "Minimum expected ECS running task count."
  type        = number
  default     = 1
}
