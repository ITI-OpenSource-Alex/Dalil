output "web_acl_arn" {
  description = "CloudFront-scope WAF Web ACL ARN."
  value       = aws_wafv2_web_acl.this.arn
}

output "web_acl_id" {
  description = "WAF Web ACL ID."
  value       = aws_wafv2_web_acl.this.id
}

output "log_group_name" {
  description = "CloudWatch log group receiving WAF logs."
  value       = aws_cloudwatch_log_group.this.name
}
