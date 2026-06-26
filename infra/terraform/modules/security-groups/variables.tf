variable "environment" {
  description = "Deployment environment name used for tagging and naming."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC where the security groups will be created."
  type        = string
}

variable "alb_ingress_cidr_blocks" {
  description = "IPv4 CIDR blocks allowed to reach the public ALB on HTTP and HTTPS."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = length(var.alb_ingress_cidr_blocks) > 0
    error_message = "alb_ingress_cidr_blocks must contain at least one CIDR block."
  }
}

variable "gateway_port" {
  description = "Port exposed by the gateway service behind the ALB."
  type        = number
  default     = 8080

  validation {
    condition     = var.gateway_port > 0 && var.gateway_port <= 65535
    error_message = "gateway_port must be between 1 and 65535."
  }
}

variable "ecs_service_ports" {
  description = "Ports exposed by internal ECS services that the gateway can call."
  type        = list(number)
  default     = [3000, 8082, 8084]

  validation {
    condition     = length(var.ecs_service_ports) > 0 && alltrue([for port in var.ecs_service_ports : port > 0 && port <= 65535])
    error_message = "ecs_service_ports must contain valid ports between 1 and 65535."
  }
}

variable "rds_port" {
  description = "Database port allowed from ECS services to RDS."
  type        = number
  default     = 5432

  validation {
    condition     = var.rds_port > 0 && var.rds_port <= 65535
    error_message = "rds_port must be between 1 and 65535."
  }
}

variable "elasticache_port" {
  description = "Cache port allowed from ECS services to ElastiCache."
  type        = number
  default     = 6379

  validation {
    condition     = var.elasticache_port > 0 && var.elasticache_port <= 65535
    error_message = "elasticache_port must be between 1 and 65535."
  }
}

variable "private_egress_cidr_blocks" {
  description = "IPv4 CIDR blocks private ECS tasks may use for outbound HTTPS through NAT."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = length(var.private_egress_cidr_blocks) > 0
    error_message = "private_egress_cidr_blocks must contain at least one CIDR block."
  }
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default     = {}
}
