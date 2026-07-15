terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "github_org" {
  type        = string
  description = "GitHub Organization or Username"
}

variable "github_repo" {
  type        = string
  description = "GitHub Repository Name"
}

# Create the OIDC Identity Provider in AWS IAM
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]

  # Standard GitHub OIDC Thumbprints
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1b511abead59c6ce207077c0bf0e0043b1382612"
  ]
}

# ---------------------------------------------------------
# Staging Deploy Role
# ---------------------------------------------------------
data "aws_iam_policy_document" "github_assume_role_staging" {
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
    # Security: Only allow assume role if triggered from the develop branch
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:ref:refs/heads/develop"]
    }
  }
}

resource "aws_iam_role" "staging_deploy" {
  name               = "goa-staging-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role_staging.json
}

# TODO: Attach specific ECS/ECR policies to aws_iam_role.staging_deploy here 

# ---------------------------------------------------------
# Production Deploy Role
# ---------------------------------------------------------
data "aws_iam_policy_document" "github_assume_role_production" {
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
    # Security: Only allow assume role if triggered by a job bound to the 'production' environment
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:environment:production"]
    }
  }
}

resource "aws_iam_role" "production_deploy" {
  name               = "goa-production-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role_production.json
}

# Output the ARNs to easily copy-paste into your GitHub workflows
output "staging_role_arn" {
  value = aws_iam_role.staging_deploy.arn
}

output "production_role_arn" {
  value = aws_iam_role.production_deploy.arn
}