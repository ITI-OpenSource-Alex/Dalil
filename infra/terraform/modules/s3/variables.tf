variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}

variable "noncurrent_version_expiration_days" {
  description = "Days after which non-current object versions are deleted"
  type        = number
  default     = 30
}

variable "force_destroy" {
  description = "Allow Terraform to delete the bucket even if it contains objects. Keep false in staging/prod."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to the bucket"
  type        = map(string)
  default     = {}
}

variable "expiration_rules" {
  description = "Current-version object expiration rules filtered by object tags."
  type = list(object({
    id     = string
    days   = number
    tags   = map(string)
    status = optional(string, "Enabled")
  }))
  default = []
}
