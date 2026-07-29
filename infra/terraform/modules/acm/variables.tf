variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "domain_name" {
  description = "Primary certificate domain name."
  type        = string
}

variable "certificate_type" {
  description = "Whether to import a generated self-signed certificate or request a public DNS-validated certificate."
  type        = string
  default     = "self_signed"

  validation {
    condition     = contains(["self_signed", "public_dns"], var.certificate_type)
    error_message = "certificate_type must be self_signed or public_dns."
  }
}

variable "subject_alternative_names" {
  description = "Additional names included in a public certificate."
  type        = list(string)
  default     = []
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone used for public certificate DNS validation."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
