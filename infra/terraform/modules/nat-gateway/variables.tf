variable "environment" {
  description = "Deployment environment name used for tagging and naming."
  type        = string
}

variable "public_subnet_ids" {
  description = "Exactly two public subnet IDs where the NAT gateways will be placed."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) == 2
    error_message = "public_subnet_ids must contain exactly two subnet IDs."
  }
}

variable "private_app_route_table_ids" {
  description = "Exactly two private application route table IDs, aligned by AZ with the public subnets."
  type        = list(string)

  validation {
    condition     = length(var.private_app_route_table_ids) == 2
    error_message = "private_app_route_table_ids must contain exactly two route table IDs."
  }
}

variable "private_data_route_table_ids" {
  description = "Exactly two private data route table IDs, aligned by AZ with the public subnets."
  type        = list(string)

  validation {
    condition     = length(var.private_data_route_table_ids) == 2
    error_message = "private_data_route_table_ids must contain exactly two route table IDs."
  }
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default     = {}
}
