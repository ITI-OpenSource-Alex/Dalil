variable "name_prefix" {
  description = "Name prefix for observability resources."
  type        = string
}

variable "service_names" {
  description = "Services requiring CloudWatch log groups and alarms."
  type        = list(string)
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days."
  type        = number
  default     = 30
}

variable "sns_topic_name" {
  description = "SNS alert topic name."
  type        = string
  default     = "goa-alerts"
}

variable "aws_region" {
  description = "AWS region rendered into CloudWatch dashboard widgets."
  type        = string
}

variable "dashboard_name" {
  description = "CloudWatch dashboard name."
  type        = string
  default     = "GOA-Overview"
}

variable "alert_email_addresses" {
  description = "Email addresses subscribed to the alert SNS topic."
  type        = list(string)
  default     = []
}

variable "sqs_queue_names" {
  description = "SQS queue names used by DLQ depth alarms."
  type        = list(string)
  default     = []
}

variable "ecs_cluster_name" {
  description = "ECS cluster name used by running task count alarms."
  type        = string
  default     = ""
}

variable "lambda_function_names" {
  description = "Lambda function names included in the invocation panel."
  type        = list(string)
  default     = []
}

variable "alarm_definitions" {
  description = "GOA-027 CloudWatch alarm definitions."
  type = map(object({
    alarm_name          = optional(string)
    description         = optional(string)
    namespace           = string
    metric_name         = string
    dimensions          = optional(map(string), {})
    comparison_operator = string
    threshold           = number
    evaluation_periods  = number
    datapoints_to_alarm = optional(number)
    period              = number
    statistic           = optional(string)
    extended_statistic  = optional(string)
    unit                = optional(string)
    treat_missing_data  = optional(string, "missing")
  }))
  default = {}

  validation {
    condition = alltrue([
      for alarm in values(var.alarm_definitions) :
      (alarm.statistic != null && alarm.extended_statistic == null) ||
      (alarm.statistic == null && alarm.extended_statistic != null)
    ])
    error_message = "Each CloudWatch alarm definition must set exactly one of statistic or extended_statistic."
  }
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
