variable "enabled" {
  description = "Whether to create the CloudFront distribution."
  type        = bool
  default     = false
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "s3_bucket_name" {
  description = "Private frontend asset bucket name."
  type        = string
  default     = null
  nullable    = true
}

variable "s3_bucket_arn" {
  description = "Private frontend asset bucket ARN."
  type        = string
  default     = null
  nullable    = true
}

variable "s3_regional_domain_name" {
  description = "Regional S3 domain name used by CloudFront."
  type        = string
  default     = null
  nullable    = true
}

variable "alb_origin_domain_name" {
  description = "API origin hostname whose TLS certificate matches the ALB listener."
  type        = string
}

variable "origin_protocol_policy" {
  description = "Protocol CloudFront uses when connecting to the ALB."
  type        = string
  default     = "https-only"

  validation {
    condition     = contains(["http-only", "https-only", "match-viewer"], var.origin_protocol_policy)
    error_message = "origin_protocol_policy must be http-only, https-only, or match-viewer."
  }
}

variable "aliases" {
  description = "Custom domains served by CloudFront."
  type        = list(string)
  default     = []
}

variable "acm_certificate_arn" {
  description = "Validated ACM certificate ARN in us-east-1."
  type        = string
  default     = null
  nullable    = true
}

variable "web_acl_arn" {
  description = "CloudFront-scope WAF Web ACL ARN."
  type        = string
  default     = null
  nullable    = true
}

variable "price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_100"
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
