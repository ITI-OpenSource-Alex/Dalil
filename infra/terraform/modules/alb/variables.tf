variable "environment" {
  description = "Deployment environment name used for tagging and naming."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC where ALB target groups will be created."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs where the internet-facing ALB will run."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) == 2
    error_message = "public_subnet_ids must contain exactly two subnet IDs."
  }
}

variable "alb_security_group_id" {
  description = "Security group ID attached to the ALB."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN used by the HTTPS listener."
  type        = string
}

variable "default_target_group_name" {
  description = "Target group key used by the HTTPS listener default action."
  type        = string
  default     = "gateway"
}

variable "target_groups" {
  description = "Target groups exposed by the ALB for the gateway and internal services."
  type = map(object({
    port                 = number
    protocol             = string
    health_check_path    = string
    deregistration_delay = number
  }))
  default = {
    gateway = {
      port                 = 8080
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    user = {
      port                 = 3000
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    speaking = {
      port                 = 8082
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
    rag = {
      port                 = 8084
      protocol             = "HTTP"
      health_check_path    = "/health"
      deregistration_delay = 30
    }
  }

  validation {
    condition = alltrue([
      for target_group in var.target_groups :
      target_group.port > 0 && target_group.port <= 65535 && contains(["HTTP", "HTTPS"], target_group.protocol)
    ])
    error_message = "Each target group must use a valid port and HTTP or HTTPS protocol."
  }
}

variable "ssl_policy" {
  description = "TLS security policy for the HTTPS listener."
  type        = string
  default     = "ELBSecurityPolicy-TLS13-1-2-2021-06"
}

variable "enable_deletion_protection" {
  description = "Whether deletion protection is enabled on the ALB."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
  default     = {}
}
