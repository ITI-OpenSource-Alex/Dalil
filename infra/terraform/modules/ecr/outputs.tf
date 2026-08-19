output "repository_urls" {
  description = "ECR repository URLs keyed by logical service name."
  value       = { for name, repository in aws_ecr_repository.this : name => repository.repository_url }
}

output "repository_arns" {
  description = "ECR repository ARNs keyed by logical service name."
  value       = { for name, repository in aws_ecr_repository.this : name => repository.arn }
}
