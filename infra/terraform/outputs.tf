output "vpc_id" {
  description = "ID of the shared VPC."
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets used by internet-facing components."
  value       = module.vpc.public_subnet_ids
}

output "private_app_subnet_ids" {
  description = "IDs of the private application subnets used by ECS/services."
  value       = module.vpc.private_app_subnet_ids
}

output "private_data_subnet_ids" {
  description = "IDs of the private data subnets used by stateful services."
  value       = module.vpc.private_data_subnet_ids
}

output "nat_gateway_ids" {
  description = "IDs of the NAT gateways that provide outbound internet access for private subnets."
  value       = module.nat_gateway.nat_gateway_ids
}

output "nat_gateway_public_ips" {
  description = "Public IPs attached to the NAT gateways."
  value       = module.nat_gateway.elastic_ip_public_ips
}

output "alb_security_group_id" {
  description = "Security group ID for the public Application Load Balancer."
  value       = module.security_groups.alb_security_group_id
}

output "gateway_security_group_id" {
  description = "Security group ID for the gateway service."
  value       = module.security_groups.gateway_security_group_id
}

output "ecs_services_security_group_id" {
  description = "Security group ID for internal ECS services."
  value       = module.security_groups.ecs_services_security_group_id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS."
  value       = module.security_groups.rds_security_group_id
}

output "elasticache_security_group_id" {
  description = "Security group ID for ElastiCache."
  value       = module.security_groups.elasticache_security_group_id
}

output "vpc_endpoint_security_group_id" {
  description = "Security group ID attached to interface VPC endpoints."
  value       = module.vpc_endpoints.interface_endpoints_security_group_id
}

output "s3_endpoint_id" {
  description = "ID of the S3 gateway VPC endpoint."
  value       = module.vpc_endpoints.s3_endpoint_id
}

output "secrets_manager_endpoint_id" {
  description = "ID of the Secrets Manager interface VPC endpoint."
  value       = module.vpc_endpoints.secrets_manager_endpoint_id
}

output "sqs_endpoint_id" {
  description = "ID of the SQS interface VPC endpoint."
  value       = module.vpc_endpoints.sqs_endpoint_id
}

output "alb_arn" {
  description = "ARN of the public Application Load Balancer."
  value       = module.alb.alb_arn
}

output "alb_dns_name" {
  description = "DNS name of the public Application Load Balancer."
  value       = module.alb.alb_dns_name
}

output "alb_zone_id" {
  description = "Canonical hosted zone ID of the public Application Load Balancer."
  value       = module.alb.alb_zone_id
}

output "alb_target_group_arns" {
  description = "ALB target group ARNs keyed by service name."
  value       = module.alb.target_group_arns
}

output "alb_https_listener_arn" {
  description = "ARN of the ALB HTTPS listener."
  value       = module.alb.https_listener_arn
}

output "ecs_task_execution_role_arns" {
  description = "Per-service ECS task execution role ARNs."
  value       = module.iam.ecs_task_execution_role_arns
}

output "ecs_task_role_arns" {
  description = "Per-service ECS task runtime role ARNs."
  value       = module.iam.ecs_task_role_arns
}

output "ecs_exec_operator_policy_arn" {
  description = "ARN of the baseline operator policy for ECS Exec."
  value       = module.iam.ecs_exec_operator_policy_arn
}

output "ecs_exec_task_policy_arn" {
  description = "ARN of the ECS Exec task policy attached to the task role."
  value       = module.iam.ecs_exec_task_policy_arn
}

output "ecs_task_execution_secrets_policy_arns" {
  description = "Per-service ECS startup secret policy ARNs."
  value       = module.iam.ecs_task_execution_secrets_policy_arns
}

output "ecs_task_app_policy_arns" {
  description = "Per-service ECS runtime application policy ARNs."
  value       = module.iam.ecs_task_app_policy_arns
}

output "session_manager_log_group_name" {
  description = "CloudWatch log group used for Session Manager logs."
  value       = module.iam.session_manager_log_group_name
}

output "session_manager_preferences_document_name" {
  description = "Name of the Session Manager preferences SSM document."
  value       = module.iam.session_manager_preferences_document_name
}

output "writing_files_bucket_name" {
  value = module.writing_files_bucket.bucket_name
}
output "exam_audio_bucket_name" {
  value = module.exam_audio_bucket.bucket_name
}
output "ingestion_reports_bucket_name" {
  value = module.ingestion_reports_bucket.bucket_name
}
output "eval_reports_bucket_name" {
  value = module.eval_reports_bucket.bucket_name
}
output "cv_processor_function_name" {
  value = try(module.cv_processor_lambda[0].function_name, null)
}
output "scholarship_matcher_function_name" {
  value = try(module.scholarship_matcher_lambda[0].function_name, null)
}
output "notification_sender_function_name" {
  value = try(module.notification_sender_lambda[0].function_name, null)
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by ECS service or Lambda worker."
  value       = module.ecr.repository_urls
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = module.ecs_cluster.cluster_name
}

output "ecs_service_names" {
  description = "ECS service names keyed by service."
  value       = { for service, service_module in module.ecs_service : service => service_module.service_name }
}

output "ecs_task_definition_arns" {
  description = "Task definition ARNs keyed by ECS service."
  value       = { for service, service_module in module.ecs_service : service => service_module.task_definition_arn }
}

output "ecs_migration_task_definition_arns" {
  description = "Migration task definition ARNs keyed by ECS service."
  value       = { for service, task_definition in aws_ecs_task_definition.migration : service => task_definition.arn }
}

output "ecs_migration_task_role_arns" {
  description = "Migration-only ECS runtime role ARNs keyed by ECS service."
  value       = { for service, role in aws_iam_role.ecs_migration_task : service => role.arn }
}

output "ecs_autoscaling_resource_ids" {
  description = "Application Auto Scaling resource IDs keyed by ECS service."
  value       = { for service, service_module in module.ecs_service : service => service_module.autoscaling_resource_id }
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, or null when disabled."
  value       = module.cloudfront.distribution_id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain, or null when disabled."
  value       = module.cloudfront.domain_name
}

output "frontend_assets_bucket_name" {
  description = "Private S3 bucket that receives the exported Next.js frontend."
  value       = try(module.frontend_assets[0].bucket_name, null)
}

output "production_hosted_zone_id" {
  description = "Production Route 53 hosted zone ID."
  value       = try(module.production_dns_zone[0].zone_id, null)
}

output "production_name_servers" {
  description = "Name servers that must be configured at the production domain registrar."
  value       = try(module.production_dns_zone[0].name_servers, [])
}

output "production_alb_certificate_arn" {
  description = "Regional ACM certificate used by the production ALB."
  value       = try(module.production_alb_certificate[0].certificate_arn, null)
}

output "production_cloudfront_certificate_arn" {
  description = "us-east-1 ACM certificate used by CloudFront."
  value       = try(module.production_cloudfront_certificate[0].certificate_arn, null)
}

output "cloudfront_waf_web_acl_arn" {
  description = "CloudFront WAF Web ACL ARN."
  value       = try(module.cloudfront_waf[0].web_acl_arn, null)
}

output "cloudfront_waf_log_group_name" {
  description = "CloudWatch log group receiving CloudFront WAF logs."
  value       = try(module.cloudfront_waf[0].log_group_name, null)
}

output "alb_waf_web_acl_arn" {
  description = "Regional WAF Web ACL ARN associated with the production ALB."
  value       = try(module.alb_waf[0].web_acl_arn, null)
}

output "alb_waf_log_group_name" {
  description = "CloudWatch log group receiving ALB WAF logs."
  value       = try(module.alb_waf[0].log_group_name, null)
}
