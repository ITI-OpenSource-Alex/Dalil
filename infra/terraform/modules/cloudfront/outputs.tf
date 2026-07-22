output "distribution_id" {
  description = "CloudFront distribution ID, or null when disabled."
  value       = try(aws_cloudfront_distribution.this[0].id, null)
}

output "domain_name" {
  description = "CloudFront distribution domain, or null when disabled."
  value       = try(aws_cloudfront_distribution.this[0].domain_name, null)
}
