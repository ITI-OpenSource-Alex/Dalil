output "goa070_service_names" {
  description = "Services covered by the GOA-070 stateful infrastructure plan."
  value       = local.service_names
}

output "goa070_postgres_databases" {
  description = "PostgreSQL database names required by GOA-070. Gateway is intentionally absent."
  value       = local.postgres_databases
}

output "goa070_redis_logical_databases" {
  description = "Reserved Redis logical database indexes."
  value       = local.redis_logical_databases
}

output "goa070_sqs_queues" {
  description = "SQS queue contract for GOA-070."
  value       = local.sqs_queues
}

output "goa070_service_secret_keys" {
  description = "Secret keys each service is allowed to consume."
  value       = local.service_secret_keys
}

output "goa070_rds_instance_class" {
  description = "Environment-specific RDS instance class."
  value       = local.rds_instance_class
}

output "goa070_redis_node_type" {
  description = "Environment-specific Redis node type."
  value       = local.redis_node_type
}

output "goa070_rds_multi_az" {
  description = "Whether RDS Multi-AZ is enabled for this environment."
  value       = local.rds_multi_az
}

output "rds_endpoint" {
  description = "RDS instance endpoint."
  value       = module.rds.instance_endpoint
}

output "rds_proxy_endpoint" {
  description = "RDS Proxy endpoint for service DATABASE_URL construction."
  value       = module.rds_proxy.proxy_endpoint
}

output "rds_database_bootstrap_sql" {
  description = "Idempotent SQL used to create the 8 service databases after RDS is reachable from private subnets."
  value       = module.rds.database_bootstrap_sql
}

output "rds_publicly_accessible" {
  description = "Whether the RDS instance is publicly accessible. Must remain false."
  value       = module.rds.publicly_accessible
}

output "redis_endpoint" {
  description = "Redis primary endpoint address."
  value       = module.elasticache.primary_endpoint_address
}

output "redis_port" {
  description = "Redis port."
  value       = module.elasticache.port
}

output "redis_logical_databases" {
  description = "Reserved Redis logical database indexes."
  value       = module.elasticache.logical_databases
}

output "sqs_queue_urls" {
  description = "SQS queue URLs by logical queue key."
  value       = module.sqs.queue_urls
}

output "sqs_queue_arns" {
  description = "SQS queue ARNs by logical queue key."
  value       = module.sqs.queue_arns
}

output "sqs_dlq_urls" {
  description = "SQS DLQ URLs by logical queue key."
  value       = module.sqs.dlq_urls
}

output "sqs_dlq_arns" {
  description = "SQS DLQ ARNs by logical queue key."
  value       = module.sqs.dlq_arns
}

output "service_secret_arns" {
  description = "Secrets Manager secret ARNs by service."
  value       = module.secrets.service_secret_arns
}

output "ecs_secret_value_from_refs" {
  description = "ECS task definition valueFrom references by service and secret key."
  value       = module.secrets.service_secret_value_from_refs
}

output "ecs_task_execution_role_arns" {
  description = "ECS task execution role ARNs by service."
  value       = module.iam.task_execution_role_arns
}

output "ecs_task_role_arns" {
  description = "ECS task role ARNs by service."
  value       = module.iam.task_role_arns
}

output "github_actions_deploy_role_arn" {
  description = "GitHub Actions OIDC deploy role ARN."
  value       = module.iam.github_deploy_role_arn
}

output "cloudwatch_log_group_names" {
  description = "CloudWatch log group names by service."
  value       = module.observability.log_group_names
}

output "sns_alert_topic_arn" {
  description = "SNS topic ARN for GOA alerts."
  value       = module.observability.sns_topic_arn
}

output "cloudwatch_alarm_arns" {
  description = "CloudWatch alarm ARNs by GOA-027 alarm key."
  value       = module.observability.alarm_arns
}
