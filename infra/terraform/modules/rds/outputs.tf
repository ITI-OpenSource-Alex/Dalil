output "instance_identifier" {
  description = "RDS instance identifier."
  value       = aws_db_instance.this.identifier
}

output "instance_endpoint" {
  description = "RDS instance endpoint."
  value       = aws_db_instance.this.endpoint
}

output "instance_address" {
  description = "RDS instance address."
  value       = aws_db_instance.this.address
}

output "instance_port" {
  description = "RDS PostgreSQL port."
  value       = aws_db_instance.this.port
}

output "security_group_id" {
  description = "RDS security group ID."
  value       = aws_security_group.this.id
}

output "master_secret_arn" {
  description = "Secrets Manager ARN containing the generated RDS master password."
  value       = var.master_secret_arn
}

output "database_names" {
  description = "Database names managed by this module."
  value       = var.database_names
}

output "database_bootstrap_sql" {
  description = "Idempotent psql script used to create the 8 GOA service databases after the instance is reachable from a private subnet."
  value       = local.database_bootstrap_sql
}

output "publicly_accessible" {
  description = "Whether the RDS instance is publicly accessible. GOA-070 requires false."
  value       = aws_db_instance.this.publicly_accessible
}

output "multi_az" {
  description = "Whether Multi-AZ is enabled for the RDS instance."
  value       = aws_db_instance.this.multi_az
}

output "backup_retention_days" {
  description = "RDS automated backup retention in days."
  value       = aws_db_instance.this.backup_retention_period
}
