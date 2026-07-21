variable "name_prefix" {
  description = "Name prefix for Secrets Manager resources."
  type        = string
}

variable "service_secret_keys" {
  description = "Secret keys that each service may consume."
  type        = map(list(string))
}

variable "database_names" {
  description = "PostgreSQL databases that require DATABASE_URL values."
  type        = map(string)
}

variable "rds_proxy_endpoint" {
  description = "RDS Proxy endpoint used when constructing service DATABASE_URL secrets."
  type        = string
  default     = ""
}

variable "rds_master_username" {
  description = "RDS master username."
  type        = string
  default     = "goa_admin"
}

variable "rds_master_password_length" {
  description = "Length of the generated RDS master password."
  type        = number
  default     = 32
}

variable "postgres_port" {
  description = "PostgreSQL port used in generated DATABASE_URL values."
  type        = number
  default     = 5432
}

variable "service_secret_values" {
  description = "Optional service secret values. Omitted keys are initialized with generated values where possible, otherwise empty strings."
  type        = map(map(string))
  default     = {}
  sensitive   = true
}

variable "kms_key_id" {
  description = "Optional KMS key ID or ARN for Secrets Manager encryption."
  type        = string
  default     = null
}

variable "recovery_window_in_days" {
  description = "Secrets Manager recovery window in days."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
