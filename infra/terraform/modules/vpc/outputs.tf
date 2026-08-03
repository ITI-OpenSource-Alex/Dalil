output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "internet_gateway_id" {
  description = "ID of the internet gateway attached to the VPC."
  value       = aws_internet_gateway.this.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets."
  value       = aws_subnet.public[*].id
}

output "private_app_subnet_ids" {
  description = "IDs of the private application subnets."
  value       = aws_subnet.private_app[*].id
}

output "private_data_subnet_ids" {
  description = "IDs of the private data subnets."
  value       = aws_subnet.private_data[*].id
}

output "public_route_table_id" {
  description = "ID of the shared public route table."
  value       = aws_route_table.public.id
}

output "private_app_route_table_ids" {
  description = "IDs of the private application route tables."
  value       = aws_route_table.private_app[*].id
}

output "private_data_route_table_ids" {
  description = "IDs of the private data route tables."
  value       = aws_route_table.private_data[*].id
}
