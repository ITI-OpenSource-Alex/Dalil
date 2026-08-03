variable "name_prefix" {
  description = "Name prefix for ElastiCache resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for the Redis security group."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Redis."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "ElastiCache must be placed in at least two private subnets."
  }
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to connect to Redis."
  type        = list(string)
  default     = []
}

variable "node_type" {
  description = "Redis node type for the environment."
  type        = string
}

variable "logical_databases" {
  description = "Reserved Redis logical database indexes."
  type        = map(number)

  validation {
    condition = (
      lookup(var.logical_databases, "gateway_rate_limits", -1) == 0 &&
      lookup(var.logical_databases, "orchestration_session_memory", -1) == 1
    )
    error_message = "Redis DB 0 must be reserved for Gateway rate limits and DB 1 for Orchestration session memory."
  }
}

variable "engine_version" {
  description = "Redis engine version."
  type        = string
  default     = "7.1"
}

variable "parameter_group_family" {
  description = "ElastiCache Redis parameter group family."
  type        = string
  default     = "redis7"
}

variable "port" {
  description = "Redis port."
  type        = number
  default     = 6379
}

variable "database_count" {
  description = "Number of logical Redis databases to expose."
  type        = number
  default     = 16
}

variable "num_cache_clusters" {
  description = "Number of Redis cache clusters in the replication group."
  type        = number
  default     = 1
}

variable "at_rest_encryption_enabled" {
  description = "Whether Redis data is encrypted at rest."
  type        = bool
  default     = true
}

variable "transit_encryption_enabled" {
  description = "Whether Redis traffic uses in-transit encryption."
  type        = bool
  default     = false
}

variable "auth_token" {
  description = "Optional Redis auth token. Requires transit_encryption_enabled to be true."
  type        = string
  default     = null
  sensitive   = true
}

variable "snapshot_retention_limit" {
  description = "Number of days Redis snapshots are retained."
  type        = number
  default     = 1
}

variable "maintenance_window" {
  description = "Preferred Redis maintenance window."
  type        = string
  default     = "sun:05:00-sun:06:00"
}

variable "apply_immediately" {
  description = "Whether Redis modifications are applied immediately."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
