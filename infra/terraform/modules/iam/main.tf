locals {
  name_prefix = "goa-${var.environment}"

  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = "iam"
      Project     = "goa"
    }
  )

  task_execution_secret_arns  = var.task_execution_secret_arns
  task_execution_kms_key_arns = var.task_execution_kms_key_arns
  task_secret_arns            = var.task_secret_arns
  task_sqs_queue_arns         = var.task_sqs_queue_arns
  task_kms_key_arns           = var.task_kms_key_arns

  create_task_execution_secrets_policy = length(local.task_execution_secret_arns) > 0 || length(local.task_execution_kms_key_arns) > 0
  create_task_app_policy               = length(local.task_secret_arns) > 0 || length(local.task_sqs_queue_arns) > 0 || length(local.task_kms_key_arns) > 0

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
  name               = "${local.name_prefix}-ecs-task-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  description        = "Execution role used by ECS to pull images, fetch startup secrets, and write logs."

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-ecs-task-execution-role"
      Role = "ecs-task-execution"
    }
  )
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  count = local.create_task_execution_secrets_policy ? 1 : 0

  dynamic "statement" {
    for_each = length(local.task_execution_secret_arns) > 0 ? [1] : []

    content {
      sid = "ReadStartupSecrets"
      actions = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
      ]
      resources = local.task_execution_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(local.task_execution_kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "DecryptStartupSecrets"
      actions   = ["kms:Decrypt"]
      resources = local.task_execution_kms_key_arns
    }
  }
}

resource "aws_iam_policy" "ecs_task_execution_secrets" {
  count = local.create_task_execution_secrets_policy ? 1 : 0

  name        = "${local.name_prefix}-ecs-task-execution-secrets-policy"
  description = "Allows the ECS task execution role to read explicitly listed startup secrets."
  policy      = data.aws_iam_policy_document.ecs_task_execution_secrets[0].json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_secrets" {
  count = local.create_task_execution_secrets_policy ? 1 : 0

  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = aws_iam_policy.ecs_task_execution_secrets[0].arn
}

resource "aws_iam_role" "ecs_task" {
  name               = "${local.name_prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  description        = "Runtime role assumed by GOA ECS application tasks."

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-ecs-task-role"
      Role = "ecs-task"
    }
  )
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
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = length(local.task_kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "DecryptEcsExecData"
      actions   = ["kms:Decrypt"]
      resources = local.task_kms_key_arns
    }
  }
}

resource "aws_iam_policy" "ecs_exec_task" {
  name        = "${local.name_prefix}-ecs-exec-task-policy"
  description = "Allows ECS tasks to open the SSM message channels required by ECS Exec."
  policy      = data.aws_iam_policy_document.ecs_exec_task.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_exec_task" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_exec_task.arn
}

data "aws_iam_policy_document" "ecs_task_app" {
  count = local.create_task_app_policy ? 1 : 0

  dynamic "statement" {
    for_each = length(local.task_secret_arns) > 0 ? [1] : []

    content {
      sid = "ReadRuntimeSecrets"
      actions = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
      ]
      resources = local.task_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(local.task_sqs_queue_arns) > 0 ? [1] : []

    content {
      sid = "UseRuntimeQueues"
      actions = [
        "sqs:ChangeMessageVisibility",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
        "sqs:ReceiveMessage",
        "sqs:SendMessage",
      ]
      resources = local.task_sqs_queue_arns
    }
  }

  dynamic "statement" {
    for_each = length(local.task_kms_key_arns) > 0 ? [1] : []

    content {
      sid = "UseRuntimeKeys"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:GenerateDataKey",
      ]
      resources = local.task_kms_key_arns
    }
  }
}

resource "aws_iam_policy" "ecs_task_app" {
  count = local.create_task_app_policy ? 1 : 0

  name        = "${local.name_prefix}-ecs-task-app-policy"
  description = "Allows ECS tasks to access explicitly listed runtime dependencies."
  policy      = data.aws_iam_policy_document.ecs_task_app[0].json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_app" {
  count = local.create_task_app_policy ? 1 : 0

  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_task_app[0].arn
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

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "session_manager" {
  name              = local.session_manager_log_group_name
  retention_in_days = var.session_manager_log_retention_days
  kms_key_id        = local.session_manager_kms_key_id != "" ? local.session_manager_kms_key_id : null

  tags = merge(
    local.common_tags,
    {
      Name = local.session_manager_log_group_name
      Role = "session-manager-logs"
    }
  )
}

resource "aws_ssm_document" "session_manager_preferences" {
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
      shellProfile = {
        linux   = ""
        windows = ""
      }
    }
  })

  tags = merge(
    local.common_tags,
    {
      Name = "SSM-SessionManagerRunShell"
      Role = "session-manager-preferences"
    }
  )
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
  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-lambda-execution-role"
      Role = "lambda-execution"
    }
  )
}

# Covers CloudWatch Logs (create group/stream, put events) plus the EC2
# network-interface actions Lambda needs to run inside the VPC.
resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda_app" {
  count = local.create_lambda_app_policy ? 1 : 0

  dynamic "statement" {
    for_each = length(local.lambda_secret_arns) > 0 ? [1] : []
    content {
      sid = "ReadLambdaSecrets"
      actions = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
      ]
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
      sid = "UseLambdaKeys"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:GenerateDataKey",
      ]
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
