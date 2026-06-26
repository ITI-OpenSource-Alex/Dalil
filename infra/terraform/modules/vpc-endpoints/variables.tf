variable "environment" {
  description = "Deployment environment name used for tagging and naming."
  type        = string
}

variable "aws_region" {
  description = "AWS region used to build regional VPC endpoint service names."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC where endpoints will be created."
  type        = string
}

variable "interface_endpoint_subnet_ids" {
  description = "Private subnet IDs for interface endpoint ENIs. Use one subnet per AZ."
  type        = list(string)

  validation {
    condition     = length(var.interface_endpoint_subnet_ids) == 2
    error_message = "interface_endpoint_subnet_ids must contain exactly two private subnet IDs."
  }
}

variable "s3_route_table_ids" {
  description = "Route table IDs that should use the S3 gateway endpoint."
  type        = list(string)

  validation {
    condition     = length(var.s3_route_table_ids) > 0
    error_message = "s3_route_table_ids must contain at least one route table ID."
  }
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to connect to interface endpoints over HTTPS."
  type        = list(string)

  validation {
    condition     = length(var.allowed_security_group_ids) > 0
    error_message = "allowed_security_group_ids must contain at least one security group ID."
  }
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default     = {}
}
