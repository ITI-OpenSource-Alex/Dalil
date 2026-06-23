output "elastic_ip_ids" {
  description = "Elastic IP allocation IDs used by the NAT gateways."
  value       = aws_eip.nat[*].id
}

output "elastic_ip_public_ips" {
  description = "Public IP addresses attached to the NAT gateways."
  value       = aws_eip.nat[*].public_ip
}

output "nat_gateway_ids" {
  description = "IDs of the NAT gateways created across the public subnets."
  value       = aws_nat_gateway.this[*].id
}
