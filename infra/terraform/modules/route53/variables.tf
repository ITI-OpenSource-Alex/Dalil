variable "enabled" {
  description = "Whether Route 53 resources are created."
  type        = bool
  default     = true
}

variable "zone_name" {
  description = "Public DNS zone name."
  type        = string
}

variable "create_zone" {
  description = "Create the hosted zone instead of using existing_zone_id."
  type        = bool
  default     = false
}

variable "existing_zone_id" {
  description = "Existing hosted zone ID when create_zone is false."
  type        = string
  default     = null
  nullable    = true
}

variable "create_root_alias" {
  description = "Create the zone-apex alias."
  type        = bool
  default     = false
}

variable "root_alias_dns_name" {
  description = "DNS name targeted by the zone-apex alias."
  type        = string
  default     = null
  nullable    = true
}

variable "root_alias_zone_id" {
  description = "Canonical hosted zone ID targeted by the zone-apex alias."
  type        = string
  default     = null
  nullable    = true
}

variable "create_api_alias" {
  description = "Create api.<zone_name> as an ALB alias."
  type        = bool
  default     = false
}

variable "api_alias_dns_name" {
  description = "ALB DNS name targeted by api.<zone_name>."
  type        = string
  default     = null
  nullable    = true
}

variable "api_alias_zone_id" {
  description = "ALB canonical hosted zone ID."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}
