output "service_secret_arns" {
  description = "Secrets Manager ARNs by service."
  value = {
    for service, secret in aws_secretsmanager_secret.service :
    service => secret.arn
  }
}

output "service_secret_value_from_refs" {
  description = "ECS valueFrom references by service and JSON key."
  value = {
    for service, keys in var.service_secret_keys :
    service => {
      for key in keys :
      key => "${aws_secretsmanager_secret.service[service].arn}:${key}::"
    }
  }
}

output "rds_master_secret_arn" {
  description = "Secrets Manager ARN for the generated RDS master credentials."
  value       = aws_secretsmanager_secret.rds_master.arn
}

output "rds_master_secret_id" {
  description = "Secrets Manager ID for the generated RDS master credentials."
  value       = aws_secretsmanager_secret.rds_master.id
}

output "rds_master_username" {
  description = "Generated RDS master credential username."
  value       = var.rds_master_username
}

output "rds_master_password" {
  description = "Generated RDS master credential password for module wiring only."
  value       = random_password.rds_master.result
  sensitive   = true
}

output "service_secret_keys" {
  description = "Secret keys that each service may consume."
  value       = var.service_secret_keys
}
