output "alb_security_group_id" {
  description = "Security group ID for the public Application Load Balancer."
  value       = aws_security_group.alb.id
}

output "gateway_security_group_id" {
  description = "Security group ID for the gateway service."
  value       = aws_security_group.gateway.id
}

output "ecs_services_security_group_id" {
  description = "Security group ID for internal ECS services."
  value       = aws_security_group.ecs_services.id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS."
  value       = aws_security_group.rds.id
}

output "elasticache_security_group_id" {
  description = "Security group ID for ElastiCache."
  value       = aws_security_group.elasticache.id
}

output "lambda_security_group_id" {
  description = "Security group ID for GOA async worker Lambdas."
  value       = aws_security_group.lambda.id
}