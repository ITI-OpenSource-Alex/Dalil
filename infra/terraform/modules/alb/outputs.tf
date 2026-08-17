output "alb_arn" {
  description = "ARN of the Application Load Balancer."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Canonical hosted zone ID of the Application Load Balancer."
  value       = aws_lb.this.zone_id
}

output "http_listener_arn" {
  description = "ARN of the HTTP listener."
  value       = one(concat(aws_lb_listener.http_redirect[*].arn, aws_lb_listener.http_forward[*].arn))
}

output "https_listener_arn" {
  description = "ARN of the HTTPS listener."
  value       = try(aws_lb_listener.https[0].arn, null)
}

output "target_group_arns" {
  description = "Target group ARNs keyed by service name."
  value       = { for name, target_group in aws_lb_target_group.this : name => target_group.arn }
}

output "target_group_names" {
  description = "Target group names keyed by service name."
  value       = { for name, target_group in aws_lb_target_group.this : name => target_group.name }
}
