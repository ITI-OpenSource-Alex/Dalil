output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "service_arn" {
  description = "ECS service ARN."
  value       = aws_ecs_service.this.id
}

output "task_definition_arn" {
  description = "Task definition ARN."
  value       = aws_ecs_task_definition.this.arn
}

output "task_definition_family" {
  description = "Task definition family, resolved by ECS to the latest ACTIVE revision."
  value       = aws_ecs_task_definition.this.family
}

output "autoscaling_resource_id" {
  description = "Application Auto Scaling resource ID."
  value       = aws_appautoscaling_target.this.resource_id
}
