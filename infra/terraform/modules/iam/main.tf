locals {
  name_prefix = "goa-${var.environment}"

  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "iam"
    Project     = "goa"
  })

  services_with_execution_policy = var.ecs_service_permissions

  services_with_task_policy = {
    for service, permissions in var.ecs_service_permissions :
    service => permissions
    if service != "db-bootstrap"
  }

  session_manager_log_group_name = coalesce(var.session_manager_log_group_name, "/aws/ssm/${local.name_prefix}/session-manager")
  session_manager_kms_key_id     = trimspace(var.session_manager_kms_key_id)
  session_manager_s3_bucket_name = trimspace(var.session_manager_s3_bucket_name)

  lambda_secret_arns       = var.lambda_secret_arns
  lambda_kms_key_arns      = var.lambda_kms_key_arns
  lambda_sqs_queue_arns    = var.lambda_sqs_queue_arns
  lambda_s3_bucket_arns    = var.lambda_s3_bucket_arns
  create_lambda_app_policy = length(local.lambda_secret_arns) > 0 || length(local.lambda_sqs_queue_arns) > 0 || length(local.lambda_s3_bucket_arns) > 0 || length(local.lambda_kms_key_arns) > 0
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

resource "aws_iam_role" "ecs_task_execution" {
  for_each = var.ecs_service_permissions

  name               = each.key == "gateway" ? "${local.name_prefix}-ecs-task-execution-role" : "${local.name_prefix}-${each.key}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  description        = each.key == "gateway" ? "Execution role used by ECS to pull images, fetch startup secrets, and write logs." : "ECS execution role for the ${each.key} service."

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-task-execution"
    Role    = "ecs-task-execution"
    Service = each.key
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  for_each = var.ecs_service_permissions

  role       = aws_iam_role.ecs_task_execution[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  for_each = local.services_with_execution_policy

  dynamic "statement" {
    for_each = length(each.value.execution_secret_arns) > 0 ? [1] : []

    content {
      sid       = "ReadOwnStartupSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = each.value.execution_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(each.value.kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "DecryptOwnStartupSecret"
      actions   = ["kms:Decrypt"]
      resources = each.value.kms_key_arns
    }
  }
}

resource "aws_iam_policy" "ecs_task_execution_secrets" {
  for_each = local.services_with_execution_policy

  name        = each.key == "gateway" ? "${local.name_prefix}-ecs-task-execution-secrets-policy" : "${local.name_prefix}-${each.key}-execution-secrets"
  description = each.key == "gateway" ? "Allows the ECS task execution role to read explicitly listed startup secrets." : "Allows ${each.key} ECS startup to read only its own secret."
  policy      = data.aws_iam_policy_document.ecs_task_execution_secrets[each.key].json
  tags        = merge(local.common_tags, { Service = each.key })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_secrets" {
  for_each = local.services_with_execution_policy

  role       = aws_iam_role.ecs_task_execution[each.key].name
  policy_arn = aws_iam_policy.ecs_task_execution_secrets[each.key].arn
}

resource "aws_iam_role" "ecs_task" {
  for_each = var.ecs_service_permissions

  name               = each.key == "gateway" ? "${local.name_prefix}-ecs-task-role" : "${local.name_prefix}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  description        = each.key == "gateway" ? "Runtime role assumed by GOA ECS application tasks." : "Least-privilege runtime role for the ${each.key} service."

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-task"
    Role    = "ecs-task"
    Service = each.key
  })
}

data "aws_iam_policy_document" "ecs_exec_task" {
  statement {
    sid = "OpenEcsExecChannels"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    # The ssmmessages channel APIs do not support resource-level permissions.
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ecs_exec_task" {
  name        = "${local.name_prefix}-ecs-exec-task-policy"
  description = "Allows ECS tasks to open the SSM message channels required by ECS Exec."
  policy      = data.aws_iam_policy_document.ecs_exec_task.json
  tags        = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_exec_task" {
  for_each = var.ecs_service_permissions

  role       = aws_iam_role.ecs_task[each.key].name
  policy_arn = aws_iam_policy.ecs_exec_task.arn
}

data "aws_iam_policy_document" "ecs_task_app" {
  for_each = local.services_with_task_policy

  dynamic "statement" {
    for_each = length(each.value.task_secret_arns) > 0 ? [1] : []

    content {
      sid       = "ReadOwnRuntimeSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = each.value.task_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(each.value.sqs_queue_arns) > 0 ? [1] : []

    content {
      sid = "UseAssignedQueues"
      actions = [
        "sqs:ChangeMessageVisibility",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
        "sqs:ReceiveMessage",
        "sqs:SendMessage",
      ]
      resources = each.value.sqs_queue_arns
    }
  }

  dynamic "statement" {
    for_each = length(each.value.s3_read_object_arns) > 0 ? [1] : []

    content {
      sid       = "ReadAssignedObjects"
      actions   = ["s3:GetObject"]
      resources = each.value.s3_read_object_arns
    }
  }

  dynamic "statement" {
    for_each = length(each.value.s3_write_object_arns) > 0 ? [1] : []

    content {
      sid       = "WriteAssignedObjects"
      actions   = ["s3:PutObject"]
      resources = each.value.s3_write_object_arns
    }
  }

  dynamic "statement" {
    for_each = length(each.value.kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "UseAssignedKeys"
      actions   = ["kms:Decrypt", "kms:DescribeKey"]
      resources = each.value.kms_key_arns
    }
  }
}

resource "aws_iam_policy" "ecs_task_app" {
  for_each = local.services_with_task_policy

  name        = each.key == "gateway" ? "${local.name_prefix}-ecs-task-app-policy" : "${local.name_prefix}-${each.key}-task-policy"
  description = each.key == "gateway" ? "Allows ECS tasks to access explicitly listed runtime dependencies." : "Least-privilege runtime permissions for ${each.key}."
  policy      = data.aws_iam_policy_document.ecs_task_app[each.key].json
  tags        = merge(local.common_tags, { Service = each.key })
}

resource "aws_iam_role_policy_attachment" "ecs_task_app" {
  for_each = local.services_with_task_policy

  role       = aws_iam_role.ecs_task[each.key].name
  policy_arn = aws_iam_policy.ecs_task_app[each.key].arn
}

data "aws_iam_policy_document" "ecs_exec_operator" {
  statement {
    sid = "ExecuteCommand"
    actions = [
      "ecs:DescribeClusters",
      "ecs:DescribeTasks",
      "ecs:ExecuteCommand",
    ]
    resources = var.ecs_exec_operator_resource_arns
  }

  statement {
    sid = "ReadSessionStatus"
    actions = [
      "ssm:DescribeSessions",
      "ssm:GetConnectionStatus",
      "ssm:ResumeSession",
      "ssm:TerminateSession",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ecs_exec_operator" {
  name        = "${local.name_prefix}-ecs-exec-operator-policy"
  description = "Baseline policy operators can attach to use ECS Exec through SSM channels."
  policy      = data.aws_iam_policy_document.ecs_exec_operator.json
  tags        = local.common_tags
}

resource "aws_cloudwatch_log_group" "session_manager" {
  name              = local.session_manager_log_group_name
  retention_in_days = var.session_manager_log_retention_days
  kms_key_id        = local.session_manager_kms_key_id != "" ? local.session_manager_kms_key_id : null
  tags              = merge(local.common_tags, { Role = "session-manager-logs" })
}

resource "aws_ssm_document" "session_manager_preferences" {
  count           = var.environment == "staging" ? 1 : 0
  name            = "SSM-SessionManagerRunShell"
  document_type   = "Session"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "1.0"
    description   = "Session Manager preferences for ${local.name_prefix}."
    sessionType   = "Standard_Stream"
    inputs = {
      cloudWatchEncryptionEnabled = local.session_manager_kms_key_id != ""
      cloudWatchLogGroupName      = aws_cloudwatch_log_group.session_manager.name
      cloudWatchStreamingEnabled  = true
      idleSessionTimeout          = tostring(var.session_manager_idle_timeout_minutes)
      kmsKeyId                    = local.session_manager_kms_key_id
      maxSessionDuration          = tostring(var.session_manager_max_duration_minutes)
      runAsDefaultUser            = var.session_manager_run_as_enabled ? var.session_manager_run_as_default_user : ""
      runAsEnabled                = var.session_manager_run_as_enabled
      s3BucketName                = local.session_manager_s3_bucket_name
      s3EncryptionEnabled         = local.session_manager_s3_bucket_name != ""
      s3KeyPrefix                 = local.session_manager_s3_bucket_name != "" ? var.session_manager_s3_key_prefix : ""
      shellProfile                = { linux = "", windows = "" }
    }
  })

  tags = merge(local.common_tags, { Role = "session-manager-preferences" })
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${local.name_prefix}-lambda-execution-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  description        = "Execution role assumed by GOA async worker Lambda functions."
  tags               = merge(local.common_tags, { Role = "lambda-execution" })
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda_app" {
  count = local.create_lambda_app_policy ? 1 : 0

  dynamic "statement" {
    for_each = length(local.lambda_secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadLambdaSecrets"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = local.lambda_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(local.lambda_sqs_queue_arns) > 0 ? [1] : []
    content {
      sid = "UseLambdaQueues"
      actions = [
        "sqs:ChangeMessageVisibility",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
        "sqs:ReceiveMessage",
        "sqs:SendMessage",
      ]
      resources = local.lambda_sqs_queue_arns
    }
  }

  dynamic "statement" {
    for_each = length(local.lambda_s3_bucket_arns) > 0 ? [1] : []
    content {
      sid       = "ReadLambdaS3Objects"
      actions   = ["s3:GetObject"]
      resources = [for arn in local.lambda_s3_bucket_arns : "${arn}/*"]
    }
  }

  dynamic "statement" {
    for_each = length(local.lambda_kms_key_arns) > 0 ? [1] : []
    content {
      sid       = "UseLambdaKeys"
      actions   = ["kms:Decrypt", "kms:DescribeKey"]
      resources = local.lambda_kms_key_arns
    }
  }
}

resource "aws_iam_policy" "lambda_app" {
  count       = local.create_lambda_app_policy ? 1 : 0
  name        = "${local.name_prefix}-lambda-app-policy"
  description = "Allows GOA Lambda workers to access explicitly listed runtime dependencies."
  policy      = data.aws_iam_policy_document.lambda_app[0].json
  tags        = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_app" {
  count      = local.create_lambda_app_policy ? 1 : 0
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_app[0].arn
}

# Preserve the former shared roles as the Gateway roles while GOA-070 expands
# the module to one isolated role pair per service.
moved {
  from = aws_iam_role.ecs_task_execution
  to   = aws_iam_role.ecs_task_execution["gateway"]
}

moved {
  from = aws_iam_role_policy_attachment.ecs_task_execution_managed
  to   = aws_iam_role_policy_attachment.ecs_task_execution_managed["gateway"]
}

moved {
  from = aws_iam_policy.ecs_task_execution_secrets[0]
  to   = aws_iam_policy.ecs_task_execution_secrets["gateway"]
}

moved {
  from = aws_iam_role_policy_attachment.ecs_task_execution_secrets[0]
  to   = aws_iam_role_policy_attachment.ecs_task_execution_secrets["gateway"]
}

moved {
  from = aws_iam_role.ecs_task
  to   = aws_iam_role.ecs_task["gateway"]
}

moved {
  from = aws_iam_role_policy_attachment.ecs_exec_task
  to   = aws_iam_role_policy_attachment.ecs_exec_task["gateway"]
}

moved {
  from = aws_iam_policy.ecs_task_app[0]
  to   = aws_iam_policy.ecs_task_app["gateway"]
}

moved {
  from = aws_iam_role_policy_attachment.ecs_task_app[0]
  to   = aws_iam_role_policy_attachment.ecs_task_app["gateway"]
}
