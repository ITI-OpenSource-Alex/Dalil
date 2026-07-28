output "ecs_task_execution_role_names" {
  description = "ECS execution role names keyed by service."
  value       = { for service, role in aws_iam_role.ecs_task_execution : service => role.name }
}

output "ecs_task_execution_role_arns" {
  description = "ECS execution role ARNs keyed by service."
  value       = { for service, role in aws_iam_role.ecs_task_execution : service => role.arn }
}

output "ecs_task_role_names" {
  description = "ECS runtime role names keyed by service."
  value       = { for service, role in aws_iam_role.ecs_task : service => role.name }
}

output "ecs_task_role_arns" {
  description = "ECS runtime role ARNs keyed by service."
  value       = { for service, role in aws_iam_role.ecs_task : service => role.arn }
}

output "ecs_exec_task_policy_arn" {
  description = "Shared ECS Exec task policy ARN."
  value       = aws_iam_policy.ecs_exec_task.arn
}

output "ecs_exec_operator_policy_arn" {
  description = "ECS Exec operator policy ARN."
  value       = aws_iam_policy.ecs_exec_operator.arn
}

output "ecs_task_execution_secrets_policy_arns" {
  description = "Per-service startup secret policy ARNs."
  value       = { for service, policy in aws_iam_policy.ecs_task_execution_secrets : service => policy.arn }
}

output "ecs_task_app_policy_arns" {
  description = "Per-service runtime policy ARNs."
  value       = { for service, policy in aws_iam_policy.ecs_task_app : service => policy.arn }
}

output "session_manager_log_group_name" {
  value = aws_cloudwatch_log_group.session_manager.name
}

output "session_manager_preferences_document_name" {
  value = try(aws_ssm_document.session_manager_preferences[0].name, null)
}

output "lambda_execution_role_name" {
  value = aws_iam_role.lambda_execution.name
}

output "lambda_execution_role_arn" {
  value = aws_iam_role.lambda_execution.arn
}

output "lambda_app_policy_arn" {
  value = try(aws_iam_policy.lambda_app[0].arn, null)
}
