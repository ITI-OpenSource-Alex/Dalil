variable "name_prefix" {
  description = "Name prefix for IAM resources."
  type        = string
}

variable "service_names" {
  description = "Services requiring ECS task roles."
  type        = list(string)

  validation {
    condition     = length(var.service_names) > 0
    error_message = "At least one service name is required."
  }
}

variable "service_secret_arns" {
  description = "Allowed Secrets Manager secret ARNs by service."
  type        = map(list(string))
  default     = {}

  validation {
    condition = alltrue(flatten([
      for service, arns in var.service_secret_arns : [
        for arn in arns : length(regexall("\\*", arn)) == 0
      ]
    ]))
    error_message = "Service task secret ARNs must be explicit and must not contain wildcards."
  }
}

variable "service_sqs_queue_arns" {
  description = "Allowed SQS queue ARNs by service."
  type        = map(list(string))
  default     = {}

  validation {
    condition = alltrue(flatten([
      for service, arns in var.service_sqs_queue_arns : [
        for arn in arns : length(regexall("\\*", arn)) == 0
      ]
    ]))
    error_message = "Service task SQS queue ARNs must be explicit and must not contain wildcards."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deploy role."
  type        = string
}

variable "github_oidc_url" {
  description = "GitHub Actions OIDC issuer URL."
  type        = string
  default     = "https://token.actions.githubusercontent.com"
}

variable "github_oidc_subjects" {
  description = "Allowed GitHub OIDC subject claims. Defaults to any workflow in github_repository."
  type        = list(string)
  default     = []
}

variable "execution_secret_arns" {
  description = "Secrets Manager secret ARNs readable by ECS task execution roles by service."
  type        = map(list(string))
  default     = {}
}

variable "execution_kms_key_arns" {
  description = "KMS key ARNs usable by ECS task execution roles by service."
  type        = map(list(string))
  default     = {}
}

variable "task_kms_key_arns" {
  description = "KMS key ARNs usable by ECS task roles by service."
  type        = map(list(string))
  default     = {}
}

variable "ecs_cluster_arn" {
  description = "ECS cluster ARN deploys may update."
  type        = string
  default     = ""
}

variable "ecs_service_arns" {
  description = "ECS service ARNs deploys may update."
  type        = list(string)
  default     = []
}

variable "ecr_repository_arns" {
  description = "ECR repository ARNs deploys may push to."
  type        = list(string)
  default     = []
}

variable "task_definition_arns" {
  description = "ECS task definition ARNs deploys may register or pass."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
