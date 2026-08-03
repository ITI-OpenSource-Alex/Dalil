output "goa070_postgres_databases" {
  value = local.postgres_databases
}

output "goa070_redis_logical_databases" {
  value = local.redis_logical_databases
}

output "rds_endpoint" {
  value = module.rds.instance_endpoint
}

output "rds_publicly_accessible" {
  description = "Security assertion: GOA PostgreSQL must remain private."
  value       = module.rds.publicly_accessible
}

output "rds_backup_retention_days" {
  value = module.rds.backup_retention_days
}

output "rds_proxy_endpoint" {
  value = try(module.rds_proxy[0].proxy_endpoint, null)
}

output "rds_database_bootstrap_sql" {
  value = module.rds.database_bootstrap_sql
}

output "redis_endpoint" {
  value = module.elasticache.primary_endpoint_address
}

output "redis_port" {
  value = module.elasticache.port
}

output "redis_logical_databases" {
  value = module.elasticache.logical_databases
}

output "sqs_queue_urls" {
  value = module.sqs.queue_urls
}

output "user_events_topic_arn" {
  value = aws_sns_topic.user_events.arn
}

output "sqs_queue_arns" {
  value = module.sqs.queue_arns
}

output "sqs_dlq_urls" {
  value = module.sqs.dlq_urls
}

output "sqs_dlq_arns" {
  value = module.sqs.dlq_arns
}

output "service_secret_arns" {
  value = module.secrets.service_secret_arns
}

output "ecs_secret_value_from_refs" {
  value = module.secrets.service_secret_value_from_refs
}

output "database_url_secret_refs" {
  description = "Secrets Manager valueFrom references for each service DATABASE_URL."
  value = {
    for service in keys(local.postgres_databases) :
    service => module.secrets.service_secret_value_from_refs[service]["DATABASE_URL"]
  }
}

output "cloudwatch_log_group_names" {
  value = module.observability.log_group_names
}

output "sns_alert_topic_arn" {
  value = module.observability.sns_topic_arn
}

output "cloudwatch_alarm_arns" {
  value = module.observability.alarm_arns
}
