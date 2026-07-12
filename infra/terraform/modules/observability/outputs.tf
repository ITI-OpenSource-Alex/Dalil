output "log_group_names" {
  description = "CloudWatch log group names by service."
  value = {
    for service, log_group in aws_cloudwatch_log_group.service :
    service => log_group.name
  }
}

output "log_group_arns" {
  description = "CloudWatch log group ARNs by service."
  value = {
    for service, log_group in aws_cloudwatch_log_group.service :
    service => log_group.arn
  }
}

output "sns_topic_arn" {
  description = "SNS topic ARN for GOA alerts."
  value       = aws_sns_topic.alerts.arn
}

output "sns_topic_name" {
  description = "SNS topic name for GOA alerts."
  value       = aws_sns_topic.alerts.name
}

output "alarm_arns" {
  description = "CloudWatch alarm ARNs by alarm key."
  value = {
    for key, alarm in aws_cloudwatch_metric_alarm.this :
    key => alarm.arn
  }
}

output "alarm_names" {
  description = "CloudWatch alarm names by alarm key."
  value = {
    for key, alarm in aws_cloudwatch_metric_alarm.this :
    key => alarm.alarm_name
  }
}

output "service_names" {
  description = "Services covered by observability resources."
  value       = var.service_names
}
