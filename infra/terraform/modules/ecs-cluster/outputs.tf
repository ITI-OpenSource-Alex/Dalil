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

output "service_names" {
  description = "ECS service names keyed by logical service."
  value       = { for name, service in aws_ecs_service.this : name => service.name }
}

output "task_definition_arns" {
  description = "Task definition ARNs keyed by logical service."
  value       = { for name, task in aws_ecs_task_definition.this : name => task.arn }
}
