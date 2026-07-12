variable "name_prefix" {
  description = "Name prefix for RDS Proxy resources."
  type        = string
}

variable "vpc_subnet_ids" {
  description = "Private subnet IDs for the RDS Proxy."
  type        = list(string)

  validation {
    condition     = length(var.vpc_subnet_ids) >= 2
    error_message = "RDS Proxy requires at least two private subnets in different availability zones."
  }
}

variable "vpc_security_group_ids" {
  description = "Security group IDs attached to the RDS Proxy."
  type        = list(string)
}

variable "db_instance_identifier" {
  description = "RDS instance identifier targeted by the proxy."
  type        = string
}

variable "db_secret_arn" {
  description = "Secrets Manager ARN used for proxy database auth."
  type        = string
}

variable "iam_role_arn" {
  description = "IAM role ARN used by RDS Proxy to read database credentials."
  type        = string
}

variable "database_names" {
  description = "Databases reachable through the proxy."
  type        = map(string)

  validation {
    condition = (
      length(var.database_names) == 8 &&
      !contains(keys(var.database_names), "gateway") &&
      !contains(values(var.database_names), "gateway_db")
    )
    error_message = "RDS Proxy must expose only the 8 service databases and must not include gateway_db."
  }
}

variable "idle_client_timeout_seconds" {
  description = "Seconds an idle client connection can remain open."
  type        = number
  default     = 1800
}

variable "connection_borrow_timeout_seconds" {
  description = "Seconds to wait for a database connection from the proxy pool."
  type        = number
  default     = 120
}

variable "max_connections_percent" {
  description = "Maximum percentage of database connections the proxy may use."
  type        = number
  default     = 90
}

variable "max_idle_connections_percent" {
  description = "Maximum percentage of idle database connections retained by the proxy."
  type        = number
  default     = 50
}

variable "session_pinning_filters" {
  description = "Session pinning filters for the default target group."
  type        = list(string)
  default     = []
}

variable "require_tls" {
  description = "Whether the RDS Proxy requires TLS from clients."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
