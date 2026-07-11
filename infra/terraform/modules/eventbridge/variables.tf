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
}

variable "target_function_arn" {
  description = "ARN of the Lambda function this rule invokes"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the rule"
  type        = map(string)
  default     = {}
}
