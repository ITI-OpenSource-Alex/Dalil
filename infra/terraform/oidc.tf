# -----------------------------------------------------------------------------
# GOA-074 / GOA-022: GitHub Actions OIDC Provider + Deploy IAM Roles
#
# Ownership model (GOA-022 B5):
#   - The OIDC identity provider is account-global. Exactly one workspace
#     creates it, gated by var.manage_github_oidc_provider (true in staging,
#     false in production).
#   - Each environment's workspace owns ITS OWN deploy role. The production
#     role no longer lives in the staging workspace, so `terraform destroy` on
#     staging can no longer take production's deploy credentials with it.
#   - Both trust policies reference the provider by constructed ARN rather
#     than by resource attribute, so the roles carry no dependency on the
#     workspace that happens to manage the provider.
# -----------------------------------------------------------------------------

locals {
  # Constructed rather than read from the resource: see the ownership note
  # above. IAM OIDC provider ARNs are fully deterministic from the issuer host.
  github_oidc_provider_arn = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"

  github_deploy_ecr_repository_arns = {
    for environment in ["staging", "production"] :
    environment => [
      for service in local.service_names :
      "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/goa-${environment}-${service}"
    ]
  }

  github_deploy_ecs_service_arns = {
    for environment in ["staging", "production"] :
    environment => [
      for service in local.service_names :
      "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:service/goa-${environment}/goa-${environment}-${service}"
    ]
  }

  github_deploy_pass_role_arns = {
    for environment in ["staging", "production"] :
    environment => flatten([
      for service in local.service_names : [
        service == "gateway" ? "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-ecs-task-execution-role" : "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-${service}-task-execution",
        service == "gateway" ? "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-ecs-task-role" : "arn:aws:iam::${var.aws_account_id}:role/goa-${environment}-${service}-task",
      ]
    ])
  }

  # Task definitions are registered per-family; RegisterTaskDefinition itself
  # takes no resource constraint, but TagResource does.
  github_deploy_task_definition_arn = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/*"
}

# -----------------------------------------------------------------------------
# OIDC Identity Provider (account-global — created by one workspace only)
# -----------------------------------------------------------------------------

data "tls_certificate" "github_actions" {
  count = var.manage_github_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.manage_github_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions[0].certificates[0].sha1_fingerprint]

  tags = merge(var.tags, {
    Name   = "github-actions-oidc"
    Ticket = "GOA-074"
  })

  # GOA-022 (N9): AWS stopped requiring thumbprint validation for the GitHub
  # provider in 2023 and now verifies against its own trusted CA store. The
  # value is still a required API field, so it is seeded once from the live
  # certificate above -- but GitHub rotates that certificate, and without this
  # block every rotation shows up as a spurious diff on an unrelated plan.
  lifecycle {
    ignore_changes = [thumbprint_list]
  }
}

# -----------------------------------------------------------------------------
# Staging Deploy Role — owned by the staging workspace
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "github_assume_staging" {
  count = var.environment == "staging" ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # GOA-022 (B3): both claim shapes are accepted, because GitHub changes the
    # `sub` claim depending on how the job is declared:
    #
    #   - a job with no `environment:` emits  ...:ref:refs/heads/dev
    #   - a job WITH `environment: staging`  emits  ...:environment:staging
    #     (the ref is dropped from the claim entirely)
    #
    # deploy-template.yml currently emits the first form. Allowing the second
    # up front means adding a GitHub Environment approval gate later is a
    # workflow-only change and does not lock the pipeline out of AWS.
    #
    # Both values are still pinned to this one repository, so no other repo
    # and no other branch can assume this role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/dev",
        "repo:${var.github_org}/${var.github_repo}:environment:staging",
      ]
    }
  }
}

resource "aws_iam_role" "staging_deploy" {
  count              = var.environment == "staging" ? 1 : 0
  name               = "goa-github-actions-staging-role"
  assume_role_policy = data.aws_iam_policy_document.github_assume_staging[0].json
  description        = "Assumed by GitHub Actions (OIDC) to deploy to staging ECS and push to staging ECR."

  tags = merge(var.tags, {
    Name        = "goa-github-actions-staging-role"
    Environment = "staging"
    Ticket      = "GOA-074"
  })
}

resource "aws_iam_role_policy" "staging_deploy" {
  count = var.environment == "staging" ? 1 : 0
  name  = "github-actions-staging-deploy-permissions"
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
          # GOA-022 (N7): repositories are IMMUTABLE, so re-running a deploy
          # for an already-pushed SHA would fail the push. The workflow calls
          # DescribeImages first and skips build/push when the tag exists.
          "ecr:DescribeImages",
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
        # Task-definition registration and lookup require wildcard resources.
        Sid      = "ManageTaskDefinitions"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"]
        Resource = "*"
      },
      {
        # GOA-022 (N4): the workflow reads the live task definition with
        # --include TAGS and carries those tags onto the new revision, and
        # RegisterTaskDefinition-with-tags is authorised by ecs:TagResource.
        Sid      = "TagTaskDefinitions"
        Effect   = "Allow"
        Action   = ["ecs:TagResource"]
        Resource = local.github_deploy_task_definition_arn
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
# Production Deploy Role — owned by the PRODUCTION workspace (GOA-022 B5)
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "github_assume_production" {
  count = var.environment == "production" ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Production is gated on the GitHub Environment approval, so the only
    # accepted claim is the environment form. A push to main alone cannot
    # assume this role -- a reviewer has to approve the deployment first.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:environment:production"]
    }
  }
}

resource "aws_iam_role" "production_deploy" {
  count              = var.environment == "production" ? 1 : 0
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
  count = var.environment == "production" ? 1 : 0
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
          "ecr:DescribeImages",
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
        # GOA-022 (B4): DescribeTaskDefinition was missing here, so the shared
        # deploy template -- which reads the live task definition before
        # rendering the new image into it -- failed with AccessDenied the
        # moment it was pointed at production. Neither API supports
        # resource-level permissions.
        Sid      = "ManageTaskDefinitions"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"]
        Resource = "*"
      },
      {
        Sid      = "TagTaskDefinitions"
        Effect   = "Allow"
        Action   = ["ecs:TagResource"]
        Resource = local.github_deploy_task_definition_arn
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
  value       = try(aws_iam_openid_connect_provider.github[0].arn, local.github_oidc_provider_arn)
}

output "staging_deploy_role_arn" {
  description = "ARN of the staging deploy IAM role. Set this as the AWS_ROLE_TO_ASSUME repository variable."
  value       = try(aws_iam_role.staging_deploy[0].arn, null)
}

output "production_deploy_role_arn" {
  description = "ARN of the production deploy IAM role (produced by the production workspace)."
  value       = try(aws_iam_role.production_deploy[0].arn, null)
}
