variable "enabled" {
  description = "Whether to create the CloudFront distribution."
  type        = bool
  default     = false
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "alb_dns_name" {
  description = "ALB DNS name used as the custom origin."
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
