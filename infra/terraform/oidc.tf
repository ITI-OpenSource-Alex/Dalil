# -----------------------------------------------------------------------------
# GOA-074: GitHub Actions OIDC Provider + Deploy IAM Roles
# -----------------------------------------------------------------------------

# Fetch the TLS certificate for GitHub's OIDC endpoint (auto-rotating thumbprint)
locals {
  github_deploy_ecr_repository_arns = {
    for environment in ["staging", "production"] :
    environment => [
      for service in local.ecr_repository_names :
      "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/goa-${environment}-${service}"
    ]
  }

  github_deploy_ecs_service_arns = {
    for environment in ["staging", "production"] :
    environment => [
      for service in local.ecs_deployed_service_names :
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:service/goa-${environment}/goa-${environment}-${service}"
    ]
  }

  github_deploy_pass_role_arns = {
    for environment in ["staging", "production"] :
    environment => flatten([
      for service in local.ecs_deployed_service_names : [
        service == "gateway" ? "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-ecs-task-execution-role" : "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-${service}-task-execution",
        service == "gateway" ? "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-ecs-task-role" : "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-${service}-task",
      ]
    ])
  }
}

data "tls_certificate" "github_actions" {
  count = var.environment == "staging" ? 1 : 0
  url   = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

# Register GitHub as an OIDC identity provider in AWS
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.environment == "staging" ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions[0].certificates[0].sha1_fingerprint]

  tags = merge(var.tags, {
    Name   = "github-actions-oidc"
    Ticket = "GOA-074"
  })
}

# -----------------------------------------------------------------------------
# Staging Deploy Role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "github_assume_staging" {
  count = var.environment == "staging" ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:ref:refs/heads/dev"]
    }
  }
}

resource "aws_iam_role" "staging_deploy" {
  count              = var.environment == "staging" ? 1 : 0
  name               = "goa-staging-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_staging[0].json
  description        = "Assumed by GitHub Actions (OIDC) to deploy to staging ECS and push to staging ECR."

  tags = merge(var.tags, {
    Name        = "goa-staging-deploy"
    Environment = "staging"
    Ticket      = "GOA-074"
  })
}

resource "aws_iam_role_policy" "staging_deploy" {
  count = var.environment == "staging" ? 1 : 0
  name  = "staging-deploy-permissions"
  role  = aws_iam_role.staging_deploy[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # GetAuthorizationToken is one of the AWS APIs that does not support
        # resource-level permissions.
        Sid      = "ECRAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
        ]
        Resource = local.github_deploy_ecr_repository_arns["staging"]
      },
      {
        Sid      = "UpdateStagingServices"
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = local.github_deploy_ecs_service_arns["staging"]
      },
      {
        # RegisterTaskDefinition does not support resource-level permissions.
        Sid      = "RegisterTaskDefinition"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition"]
        Resource = "*"
      },
      {
        Sid      = "PassRoleToECS"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = local.github_deploy_pass_role_arns["staging"]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      },
    ]
  })
}

# -----------------------------------------------------------------------------
# Production Deploy Role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "github_assume_production" {
  count = var.environment == "staging" ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Uses environment claim — requires the GitHub Environment approval gate
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:environment:production"]
    }
  }
}

resource "aws_iam_role" "production_deploy" {
  count              = var.environment == "staging" ? 1 : 0
  name               = "goa-production-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_production[0].json
  description        = "Assumed by GitHub Actions (OIDC) to deploy to production ECS and push to production ECR."

  tags = merge(var.tags, {
    Name        = "goa-production-deploy"
    Environment = "production"
    Ticket      = "GOA-074"
  })
}

resource "aws_iam_role_policy" "production_deploy" {
  count = var.environment == "staging" ? 1 : 0
  name  = "production-deploy-permissions"
  role  = aws_iam_role.production_deploy[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECRAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
        ]
        Resource = local.github_deploy_ecr_repository_arns["production"]
      },
      {
        Sid      = "UpdateProductionServices"
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = local.github_deploy_ecs_service_arns["production"]
      },
      {
        # RegisterTaskDefinition does not support resource-level permissions.
        Sid      = "RegisterTaskDefinition"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition"]
        Resource = "*"
      },
      {
        Sid      = "PassRoleToECS"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = local.github_deploy_pass_role_arns["production"]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      },
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider registered in AWS IAM."
  value       = try(aws_iam_openid_connect_provider.github[0].arn, null)
}

output "staging_deploy_role_arn" {
  description = "ARN of the staging deploy IAM role (use in deploy-staging.yml)."
  value       = try(aws_iam_role.staging_deploy[0].arn, null)
}

output "production_deploy_role_arn" {
  description = "ARN of the production deploy IAM role (use in deploy-production.yml)."
  value       = try(aws_iam_role.production_deploy[0].arn, null)
}
