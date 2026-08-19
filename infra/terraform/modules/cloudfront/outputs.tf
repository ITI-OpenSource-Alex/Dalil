output "distribution_id" {
  description = "CloudFront distribution ID, or null when disabled."
  value       = try(aws_cloudfront_distribution.this[0].id, null)
}

output "domain_name" {
  description = "CloudFront distribution domain, or null when disabled."
  value       = try(aws_cloudfront_distribution.this[0].domain_name, null)
}

output "hosted_zone_id" {
  description = "CloudFront canonical hosted zone ID, or null when disabled."
  value       = try(aws_cloudfront_distribution.this[0].hosted_zone_id, null)
}

output "distribution_arn" {
  description = "CloudFront distribution ARN, or null when disabled."
  value       = try(aws_cloudfront_distribution.this[0].arn, null)
}
