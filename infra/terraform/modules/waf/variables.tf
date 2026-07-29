variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "scope" {
  description = "WAF scope: CLOUDFRONT for the CDN or REGIONAL for the ALB."
  type        = string
  default     = "CLOUDFRONT"

  validation {
    condition     = contains(["CLOUDFRONT", "REGIONAL"], var.scope)
    error_message = "scope must be CLOUDFRONT or REGIONAL."
  }
}

variable "association_resource_arn" {
  description = "Regional resource ARN associated directly with this ACL."
  type        = string
  default     = null
  nullable    = true
}

variable "log_group_name" {
  description = "WAF log group name. AWS requires the aws-waf-logs- prefix."
  type        = string

  validation {
    condition     = startswith(var.log_group_name, "aws-waf-logs-")
    error_message = "WAF log_group_name must begin with aws-waf-logs-."
  }
}

variable "rate_limit" {
  description = "Maximum requests allowed from one IP during WAF's five-minute evaluation window."
  type        = number
  default     = 1000

  validation {
    condition     = var.rate_limit >= 100
    error_message = "rate_limit must be at least 100."
  }
}

variable "log_retention_days" {
  description = "CloudWatch retention for WAF logs."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
