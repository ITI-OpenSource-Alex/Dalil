output "interface_endpoints_security_group_id" {
  description = "Security group ID attached to interface VPC endpoints."
  value       = aws_security_group.interface_endpoints.id
}

output "s3_endpoint_id" {
  description = "ID of the S3 gateway VPC endpoint."
  value       = aws_vpc_endpoint.s3.id
}

output "secrets_manager_endpoint_id" {
  description = "ID of the Secrets Manager interface VPC endpoint."
  value       = aws_vpc_endpoint.secrets_manager.id
}

output "sqs_endpoint_id" {
  description = "ID of the SQS interface VPC endpoint."
  value       = aws_vpc_endpoint.sqs.id
}

output "interface_endpoint_ids" {
  description = "IDs of interface VPC endpoints."
  value = {
    secrets_manager = aws_vpc_endpoint.secrets_manager.id
    sqs             = aws_vpc_endpoint.sqs.id
  }
}

output "interface_endpoint_dns_entries" {
  description = "DNS entries for interface VPC endpoints."
  value = {
    secrets_manager = aws_vpc_endpoint.secrets_manager.dns_entry
    sqs             = aws_vpc_endpoint.sqs.dns_entry
  }
}
