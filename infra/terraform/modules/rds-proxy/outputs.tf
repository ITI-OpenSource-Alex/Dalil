output "proxy_arn" {
  description = "RDS Proxy ARN."
  value       = aws_db_proxy.this.arn
}

output "proxy_name" {
  description = "RDS Proxy name."
  value       = aws_db_proxy.this.name
}

output "proxy_endpoint" {
  description = "RDS Proxy endpoint."
  value       = aws_db_proxy.this.endpoint
}

output "target_group_arn" {
  description = "RDS Proxy target group ARN."
  value       = aws_db_proxy_default_target_group.this.arn
}

output "target_id" {
  description = "RDS Proxy target resource ID."
  value       = aws_db_proxy_target.this.id
}

output "database_names" {
  description = "Databases reachable through the proxy."
  value       = var.database_names
}

output "database_url_host" {
  description = "Host value to use when building service DATABASE_URL secrets."
  value       = aws_db_proxy.this.endpoint
}
