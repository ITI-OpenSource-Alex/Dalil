variable "name_prefix" {
  description = "Environment-qualified prefix used for repository names."
  type        = string
}

variable "repositories" {
  description = "Logical repository names to create."
  type        = set(string)
}

variable "image_retention_count" {
  description = "Maximum number of images retained per repository."
  type        = number
  default     = 10
}

variable "tags" {
  description = "Common tags applied to all repositories."
  type        = map(string)
  default     = {}
}
