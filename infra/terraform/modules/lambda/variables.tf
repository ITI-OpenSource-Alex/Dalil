variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "package_type" {
  description = "Lambda deployment package type"
  type        = string
  default     = "Image"
}

variable "image_uri" {
  description = "Container image URI for the Lambda function"
  type        = string
  default     = null
}

variable "filename" {
  description = "Zip deployment package filename for the Lambda function"
  type        = string
  default     = null
}

variable "handler" {
  description = "Handler for Zip-based Lambda deployments"
  type        = string
  default     = null
}

variable "runtime" {
  description = "Runtime for Zip-based Lambda deployments"
  type        = string
  default     = null
}

variable "lambda_insights_layer_arn" {
  description = "ARN of the AWS-managed Lambda Insights extension layer for this region/arch"
  type        = string
  default     = ""
}

variable "enable_lambda_insights" {
  description = "Enable the Lambda Insights extension layer"
  type        = bool
  default     = true
}

variable "role_arn" {
  description = "ARN of the IAM execution role (from the iam module)"
  type        = string
}

variable "timeout" {
  description = "Function timeout in seconds"
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "Memory allocated to the function, in MB"
  type        = number
  default     = 512
}

variable "reserved_concurrent_executions" {
  description = "Reserved concurrency limit. Set to -1 for unreserved (account pool)."
  type        = number
  default     = -1
}

variable "vpc_subnet_ids" {
  description = "Private subnet IDs to attach the function to (from the vpc module)"
  type        = list(string)
}

variable "vpc_security_group_ids" {
  description = "Security group IDs to attach the function to"
  type        = list(string)
}

variable "environment_variables" {
  description = "Environment variables for the function"
  type        = map(string)
  default     = {}
}

variable "enable_tracing" {
  description = "Enable X-Ray active tracing"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to the function"
  type        = map(string)
  default     = {}
}
