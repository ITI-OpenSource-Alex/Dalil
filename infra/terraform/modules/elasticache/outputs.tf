output "cluster_id" {
  description = "ElastiCache Redis cluster ID."
  value       = aws_elasticache_replication_group.this.id
}

output "replication_group_id" {
  description = "ElastiCache Redis replication group ID."
  value       = aws_elasticache_replication_group.this.replication_group_id
}

output "primary_endpoint_address" {
  description = "Redis primary endpoint address."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "port" {
  description = "Redis port."
  value       = aws_elasticache_replication_group.this.port
}

output "security_group_id" {
  description = "Redis security group ID."
  value       = aws_security_group.this.id
}

output "logical_databases" {
  description = "Reserved Redis logical database indexes."
  value       = var.logical_databases
}

output "gateway_rate_limit_database" {
  description = "Redis logical database reserved for Gateway rate limits."
  value       = var.logical_databases["gateway_rate_limits"]
}

output "orchestration_session_memory_database" {
  description = "Redis logical database reserved for Orchestration session memory."
  value       = var.logical_databases["orchestration_session_memory"]
}

output "subnet_group_name" {
  description = "ElastiCache subnet group name."
  value       = aws_elasticache_subnet_group.this.name
}
