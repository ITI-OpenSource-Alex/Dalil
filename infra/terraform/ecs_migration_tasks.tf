data "aws_iam_policy_document" "ecs_migration_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_migration_task" {
  for_each = local.ecs_services

  name               = "${local.name_prefix}-${each.key}-migration-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_migration_assume_role.json
  description        = "Runtime role for the ${each.key} migration task. No SQS, S3, SNS, or external API permissions are attached."

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-migration-task"
    Role    = "ecs-migration-task"
    Service = each.key
  })
}

resource "aws_ecs_task_definition" "migration" {
  for_each = local.ecs_services

  family                   = "${local.name_prefix}-${each.key}-migration"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = module.iam.ecs_task_execution_role_arns[each.key]
  task_role_arn            = aws_iam_role.ecs_migration_task[each.key].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = each.key
    image     = each.value.image
    essential = true
    command   = local.ecs_migration_commands[each.key]
    environment = [
      for name, value in each.value.environment : {
        name  = name
        value = value
      }
    ]
    secrets = [
      for name, value_from in each.value.secrets : {
        name      = name
        valueFrom = value_from
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = module.observability.log_group_names[each.key]
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "${each.key}-migration"
      }
    }
  }])

  tags = merge(local.common_tags, {
    Role = "ecs-migration-task-definition"
  })
}
