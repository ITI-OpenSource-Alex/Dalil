variable "rule_name" {
  description = "Name of the EventBridge rule"
  type        = string
}

variable "description" {
  description = "Description of the rule"
  type        = string
  default     = ""
}

variable "schedule_expression" {
  description = "AWS schedule expression, e.g. \"cron(0 2 ? * SUN *)\" or \"rate(5 minutes)\". Must already be in AWS's 6-field cron syntax, not crontab's 5-field syntax."
  type        = string
}

variable "target_function_name" {
  description = "Name of the Lambda function this rule invokes"
  type        = string
  default     = null
  nullable    = true
}

variable "target_function_arn" {
  description = "Target ARN: Lambda function ARN or ECS cluster ARN."
  type        = string
}

variable "target_type" {
  description = "EventBridge target kind."
  type        = string
  default     = "lambda"

  validation {
    condition     = contains(["lambda", "ecs", "sqs"], var.target_type)
    error_message = "target_type must be lambda, ecs, or sqs."
  }
}

variable "input" {
  description = "Constant JSON passed to the target."
  type        = string
  default     = null
  nullable    = true
}

variable "maximum_retry_attempts" {
  type    = number
  default = 2
}

variable "maximum_event_age_in_seconds" {
  type    = number
  default = 3600
}

variable "dlq_arn" {
  type     = string
  default  = null
  nullable = true
}

variable "target_role_arn" {
  type     = string
  default  = null
  nullable = true
}

variable "ecs_task_definition_arn" {
  description = "ECS task definition ARN or family. A family resolves to the latest ACTIVE revision."
  type        = string
  default     = null
  nullable    = true
}

variable "ecs_subnet_ids" {
  type    = list(string)
  default = []
}

variable "ecs_security_group_ids" {
  type    = list(string)
  default = []
}

variable "tags" {
  description = "Tags to apply to the rule"
  type        = map(string)
  default     = {}
}
