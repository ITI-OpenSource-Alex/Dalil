output "ecs_task_execution_role_name" {
  description = "Name of the ECS task execution role."
  value       = aws_iam_role.ecs_task_execution.name
}

output "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution role."
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_name" {
  description = "Name of the ECS task runtime role."
  value       = aws_iam_role.ecs_task.name
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task runtime role."
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_exec_task_policy_arn" {
  description = "ARN of the ECS Exec task policy attached to the ECS task role."
  value       = aws_iam_policy.ecs_exec_task.arn
}

output "ecs_exec_operator_policy_arn" {
  description = "ARN of the baseline operator policy for ECS Exec."
  value       = aws_iam_policy.ecs_exec_operator.arn
}

output "ecs_task_execution_secrets_policy_arn" {
  description = "ARN of the optional ECS task execution secrets policy, if created."
  value       = try(aws_iam_policy.ecs_task_execution_secrets[0].arn, null)
}

output "ecs_task_app_policy_arn" {
  description = "ARN of the optional ECS task runtime application policy, if created."
  value       = try(aws_iam_policy.ecs_task_app[0].arn, null)
}

output "session_manager_log_group_name" {
  description = "CloudWatch log group used for Session Manager logs."
  value       = aws_cloudwatch_log_group.session_manager.name
}

output "session_manager_preferences_document_name" {
  description = "Name of the Session Manager preferences SSM document."
  value       = try(aws_ssm_document.session_manager_preferences[0].name, null)
}

output "lambda_execution_role_name" {
  description = "Name of the Lambda execution role."
  value       = aws_iam_role.lambda_execution.name
}
output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role."
  value       = aws_iam_role.lambda_execution.arn
}
output "lambda_app_policy_arn" {
  description = "ARN of the optional Lambda runtime application policy, if created."
  value       = try(aws_iam_policy.lambda_app[0].arn, null)
}
