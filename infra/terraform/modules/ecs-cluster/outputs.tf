output "cluster_id" {
  description = "ECS cluster ID."
  value       = aws_ecs_cluster.this.id
}

output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "service_connect_namespace_arn" {
  description = "Cloud Map HTTP namespace ARN used by ECS Service Connect."
  value       = aws_service_discovery_http_namespace.this.arn
}

output "service_connect_namespace_name" {
  description = "ECS Service Connect namespace name."
  value       = aws_service_discovery_http_namespace.this.name
}
