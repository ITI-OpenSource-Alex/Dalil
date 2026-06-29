output "task_execution_role_arns" {
  description = "ECS task execution role ARNs by service."
  value = {
    for service, role in aws_iam_role.task_execution :
    service => role.arn
  }
}

output "task_execution_role_names" {
  description = "ECS task execution role names by service."
  value = {
    for service, role in aws_iam_role.task_execution :
    service => role.name
  }
}

output "task_role_arns" {
  description = "ECS task role ARNs by service."
  value = {
    for service, role in aws_iam_role.task :
    service => role.arn
  }
}

output "task_role_names" {
  description = "ECS task role names by service."
  value = {
    for service, role in aws_iam_role.task :
    service => role.name
  }
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC provider ARN."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "github_deploy_role_arn" {
  description = "GitHub Actions deploy role ARN."
  value       = aws_iam_role.github_deploy.arn
}

output "github_deploy_role_name" {
  description = "GitHub Actions deploy role name."
  value       = aws_iam_role.github_deploy.name
}

output "github_oidc_subjects" {
  description = "Allowed GitHub OIDC subject claims."
  value       = local.github_subjects
}

output "service_names" {
  description = "Services requiring IAM roles."
  value       = var.service_names
}
