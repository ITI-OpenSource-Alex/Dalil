variable "project_name" {
  description = "Short project name used for resource naming."
  type        = string
  default     = "goa"
}

variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be either staging or production."
  }
}

variable "aws_region" {
  description = "AWS region for all regional resources."
  type        = string
}

variable "aws_skip_credentials_validation" {
  description = "Skip AWS credentials validation for offline plans only."
  type        = bool
  default     = false
}

variable "aws_skip_metadata_api_check" {
  description = "Skip AWS metadata API checks for offline plans only."
  type        = bool
  default     = false
}

variable "aws_skip_requesting_account_id" {
  description = "Skip requesting the AWS account ID for offline plans only."
  type        = bool
  default     = false
}

variable "aws_skip_region_validation" {
  description = "Skip AWS region validation for offline plans only."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "VPC CIDR block from the GOA-069 network foundation."
  type        = string
}

variable "availability_zones" {
  description = "Availability zones for the environment."
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks from the GOA-069 network foundation."
  type        = list(string)
}

variable "private_app_subnet_cidrs" {
  description = "Private app subnet CIDR blocks from the GOA-069 network foundation."
  type        = list(string)
}

variable "private_data_subnet_cidrs" {
  description = "Private data subnet CIDR blocks from the GOA-069 network foundation."
  type        = list(string)
}

variable "domain_name" {
  description = "Primary DNS name for the environment."
  type        = string
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone ID for the environment domain."
  type        = string
}

variable "alb_certificate_arn" {
  description = "ACM certificate ARN for the application load balancer."
  type        = string
}

variable "alb_enable_deletion_protection" {
  description = "Whether ALB deletion protection is enabled."
  type        = bool
}

variable "alb_default_target_group_name" {
  description = "Default ALB target group name."
  type        = string
}

variable "task_execution_secret_arns" {
  description = "Existing secret ARNs readable by ECS task execution roles."
  type        = list(string)
  default     = []
}

variable "task_execution_kms_key_arns" {
  description = "Existing KMS key ARNs usable by ECS task execution roles."
  type        = list(string)
  default     = []
}

variable "task_secret_arns" {
  description = "Existing secret ARNs readable by ECS task roles."
  type        = list(string)
  default     = []
}

variable "task_sqs_queue_arns" {
  description = "Existing SQS queue ARNs usable by ECS task roles."
  type        = list(string)
  default     = []
}

variable "task_kms_key_arns" {
  description = "Existing KMS key ARNs usable by ECS task roles."
  type        = list(string)
  default     = []
}

variable "ecs_exec_operator_resource_arns" {
  description = "Resource ARNs operators may access through ECS Exec."
  type        = list(string)
  default     = []
}

variable "session_manager_log_retention_days" {
  description = "CloudWatch retention for Session Manager logs."
  type        = number
  default     = 30
}

variable "session_manager_kms_key_id" {
  description = "Optional KMS key ID for Session Manager logs."
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deploy role through OIDC."
  type        = string
  default     = "org/goa-repo"
}

variable "alert_email_addresses" {
  description = "Email addresses subscribed to the goa-alerts SNS topic."
  type        = list(string)
  default     = []
}

variable "goa069_vpc_id" {
  description = "VPC ID output from GOA-069."
  type        = string
}

variable "goa069_private_app_subnet_ids" {
  description = "Private app subnet IDs output from GOA-069."
  type        = list(string)
}

variable "goa069_private_data_subnet_ids" {
  description = "Private data subnet IDs output from GOA-069."
  type        = list(string)
}

variable "goa069_workload_security_group_ids" {
  description = "Security group IDs used by ECS and Lambda workloads from GOA-069."
  type        = list(string)
}

variable "goa069_ecs_cluster_name" {
  description = "ECS cluster name output from GOA-069."
  type        = string
}

variable "goa069_ecs_cluster_arn" {
  description = "ECS cluster ARN output from GOA-069."
  type        = string
  default     = ""
}

variable "goa069_ecs_service_names" {
  description = "ECS service names by GOA service key from GOA-069. Defaults to name_prefix-service when omitted."
  type        = map(string)
  default     = {}
}

variable "goa069_ecs_service_arns" {
  description = "ECS service ARNs by GOA service key from GOA-069."
  type        = map(string)
  default     = {}
}

variable "goa069_ecr_repository_arns" {
  description = "ECR repository ARNs by GOA service key from GOA-069."
  type        = map(string)
  default     = {}
}

variable "goa069_task_definition_arns" {
  description = "ECS task definition ARNs by GOA service key from GOA-069."
  type        = map(string)
  default     = {}
}

variable "service_secret_values" {
  description = "Optional service secret values. Omitted keys are initialized by the secrets module where possible."
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
  description = "Optional Redis auth token. Requires redis_transit_encryption_enabled to be true."
  type        = string
  default     = null
  sensitive   = true
}

variable "speaking_p95_latency_threshold_ms" {
  description = "GOA-027 Speaking P95 latency alarm threshold in milliseconds."
  type        = number
  default     = 2000
}

variable "service_error_rate_threshold" {
  description = "GOA-027 service error rate alarm threshold."
  type        = number
  default     = 5
}

variable "dlq_visible_messages_threshold" {
  description = "GOA-027 DLQ visible message count alarm threshold."
  type        = number
  default     = 1
}

variable "ecs_running_task_minimum" {
  description = "GOA-027 ECS running task minimum threshold."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
