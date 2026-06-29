locals {
  services = toset(var.service_names)

  github_oidc_host = replace(var.github_oidc_url, "https://", "")
  github_subjects  = length(var.github_oidc_subjects) > 0 ? var.github_oidc_subjects : ["repo:${var.github_repository}:*"]

  task_secret_arns_by_service = {
    for service in var.service_names :
    service => distinct(lookup(var.service_secret_arns, service, []))
  }

  task_sqs_queue_arns_by_service = {
    for service in var.service_names :
    service => distinct(lookup(var.service_sqs_queue_arns, service, []))
  }

  task_kms_key_arns_by_service = {
    for service in var.service_names :
    service => distinct(lookup(var.task_kms_key_arns, service, []))
  }

  execution_secret_arns_by_service = {
    for service in var.service_names :
    service => distinct(lookup(var.execution_secret_arns, service, []))
  }

  execution_kms_key_arns_by_service = {
    for service in var.service_names :
    service => distinct(lookup(var.execution_kms_key_arns, service, []))
  }

}

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  for_each = local.services

  name               = "${var.name_prefix}-${each.key}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${each.key}-ecs-execution"
    Service = each.key
    Role    = "ecs-task-execution"
  })
}

resource "aws_iam_role" "task" {
  for_each = local.services

  name               = "${var.name_prefix}-${each.key}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${each.key}-ecs-task"
    Service = each.key
    Role    = "ecs-task"
  })
}

data "aws_iam_policy_document" "task" {
  for_each = local.services

  dynamic "statement" {
    for_each = length(local.task_secret_arns_by_service[each.key]) > 0 ? [1] : []

    content {
      sid = "ReadServiceSecrets"
      actions = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
      ]
      resources = local.task_secret_arns_by_service[each.key]
    }
  }

  dynamic "statement" {
    for_each = length(local.task_sqs_queue_arns_by_service[each.key]) > 0 ? [1] : []

    content {
      sid = "UseServiceQueues"
      actions = [
        "sqs:ChangeMessageVisibility",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
        "sqs:ReceiveMessage",
        "sqs:SendMessage",
      ]
      resources = local.task_sqs_queue_arns_by_service[each.key]
    }
  }

  dynamic "statement" {
    for_each = length(local.task_kms_key_arns_by_service[each.key]) > 0 ? [1] : []

    content {
      sid = "UseServiceKmsKeys"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
      ]
      resources = local.task_kms_key_arns_by_service[each.key]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  for_each = data.aws_iam_policy_document.task

  name   = "${var.name_prefix}-${each.key}-ecs-task"
  role   = aws_iam_role.task[each.key].id
  policy = each.value.json
}

data "aws_iam_policy_document" "task_execution" {
  for_each = local.services

  dynamic "statement" {
    for_each = length(local.execution_secret_arns_by_service[each.key]) > 0 ? [1] : []

    content {
      sid = "ReadStartupSecrets"
      actions = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
      ]
      resources = local.execution_secret_arns_by_service[each.key]
    }
  }

  dynamic "statement" {
    for_each = length(local.execution_kms_key_arns_by_service[each.key]) > 0 ? [1] : []

    content {
      sid = "DecryptStartupSecrets"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
      ]
      resources = local.execution_kms_key_arns_by_service[each.key]
    }
  }
}

resource "aws_iam_role_policy" "task_execution" {
  for_each = data.aws_iam_policy_document.task_execution

  name   = "${var.name_prefix}-${each.key}-ecs-execution"
  role   = aws_iam_role.task_execution[each.key].id
  policy = each.value.json
}

data "tls_certificate" "github" {
  url = var.github_oidc_url
}

resource "aws_iam_openid_connect_provider" "github" {
  url = var.github_oidc_url

  client_id_list = [
    "sts.amazonaws.com",
  ]

  thumbprint_list = [
    data.tls_certificate.github.certificates[0].sha1_fingerprint,
  ]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-github-actions-oidc"
  })
}

data "aws_iam_policy_document" "github_deploy_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.github_oidc_host}:sub"
      values   = local.github_subjects
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_deploy_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-github-deploy"
    Role = "github-actions-deploy"
  })
}

data "aws_iam_policy_document" "github_deploy" {
  dynamic "statement" {
    for_each = length(var.ecs_service_arns) > 0 ? [1] : []

    content {
      sid       = "UpdateEcsServices"
      actions   = ["ecs:UpdateService"]
      resources = var.ecs_service_arns
    }
  }

  dynamic "statement" {
    for_each = length(var.ecr_repository_arns) > 0 ? [1] : []

    content {
      sid       = "PushEcrImages"
      actions   = ["ecr:PutImage"]
      resources = var.ecr_repository_arns
    }
  }

  statement {
    sid       = "RegisterTaskDefinitions"
    actions   = ["ecs:RegisterTaskDefinition"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${var.name_prefix}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
