# -----------------------------------------------------------------------------
# GOA-074: GitHub Actions OIDC Provider + Deploy IAM Roles
# -----------------------------------------------------------------------------

# Fetch the TLS certificate for GitHub's OIDC endpoint (auto-rotating thumbprint)
data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

# Register GitHub as an OIDC identity provider in AWS
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]

  tags = merge(var.tags, {
    Name   = "github-actions-oidc"
    Ticket = "GOA-074"
  })
}

# -----------------------------------------------------------------------------
# Staging Deploy Role
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "github_assume_staging" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
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
  name               = "goa-staging-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_staging.json
  description        = "Assumed by GitHub Actions (OIDC) to deploy to staging ECS and push to staging ECR."

  tags = merge(var.tags, {
    Name        = "goa-staging-deploy"
    Environment = "staging"
    Ticket      = "GOA-074"
  })
}

resource "aws_iam_role_policy" "staging_deploy" {
  name = "staging-deploy-permissions"
  role = aws_iam_role.staging_deploy.id

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
        Resource = "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/goa-*"
      },
      {
        Sid    = "ECSDeployServices"
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:RegisterTaskDefinition",
          "ecs:ListTasks",
          "ecs:DescribeTasks",
        ]
        Resource = "*"
      },
      {
        Sid      = "PassRoleToECS"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = "*"
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
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
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
  name               = "goa-production-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_production.json
  description        = "Assumed by GitHub Actions (OIDC) to deploy to production ECS and push to production ECR."

  tags = merge(var.tags, {
    Name        = "goa-production-deploy"
    Environment = "production"
    Ticket      = "GOA-074"
  })
}

resource "aws_iam_role_policy" "production_deploy" {
  name = "production-deploy-permissions"
  role = aws_iam_role.production_deploy.id

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
        Resource = "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/goa-*"
      },
      {
        Sid    = "ECSDeployServices"
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:RegisterTaskDefinition",
          "ecs:ListTasks",
          "ecs:DescribeTasks",
        ]
        Resource = "*"
      },
      {
        Sid      = "PassRoleToECS"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = "*"
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
  value       = aws_iam_openid_connect_provider.github.arn
}

output "staging_deploy_role_arn" {
  description = "ARN of the staging deploy IAM role (use in deploy-staging.yml)."
  value       = aws_iam_role.staging_deploy.arn
}

output "production_deploy_role_arn" {
  description = "ARN of the production deploy IAM role (use in deploy-production.yml)."
  value       = aws_iam_role.production_deploy.arn
}
