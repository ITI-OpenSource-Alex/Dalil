locals {
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "ecs-cluster"
    Project     = "goa"
  })
}

resource "aws_cloudwatch_log_group" "exec" {
  name              = "/aws/ecs/${var.name_prefix}/exec"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  configuration {
    execute_command_configuration {
      logging = "OVERRIDE"

      log_configuration {
        cloud_watch_encryption_enabled = false
        cloud_watch_log_group_name     = aws_cloudwatch_log_group.exec.name
      }
    }
  }

  tags = local.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = var.environment == "production" ? "FARGATE" : "FARGATE_SPOT"
    weight            = 1
  }
}

resource "aws_ecs_task_definition" "this" {
  for_each = var.services

  family                   = "${var.name_prefix}-${each.key}"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = var.task_execution_role_arns[each.key]
  task_role_arn            = var.task_role_arns[each.key]

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = each.key
    image     = each.value.image
    essential = true
    portMappings = [{
      name          = each.key
      containerPort = each.value.container_port
      hostPort      = each.value.container_port
      protocol      = "tcp"
      appProtocol   = "http"
    }]
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
        awslogs-group         = "/aws/ecs/${var.name_prefix}/${each.key}"
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = each.key
      }
    }
  }])

  tags = merge(local.common_tags, { Service = each.key })
}

data "aws_region" "current" {}

resource "aws_ecs_service" "this" {
  for_each = var.services

  name                   = "${var.name_prefix}-${each.key}"
  cluster                = aws_ecs_cluster.this.id
  task_definition        = aws_ecs_task_definition.this[each.key].arn
  desired_count          = each.value.desired_count
  enable_execute_command = true
  launch_type            = "FARGATE"
  propagate_tags         = "SERVICE"

  deployment_minimum_healthy_percent = each.value.desired_count > 1 ? 50 : 0
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = each.value.attach_to_load_balancer ? each.value.health_check_grace_period_seconds : null

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = false
    subnets          = var.private_subnet_ids
    security_groups = [
      each.key == "gateway" ? var.gateway_security_group_id : var.services_security_group_id,
    ]
  }

  dynamic "load_balancer" {
    for_each = each.value.attach_to_load_balancer ? [1] : []

    content {
      target_group_arn = var.target_group_arns[each.key]
      container_name   = each.key
      container_port   = each.value.container_port
    }
  }

  depends_on = [aws_ecs_cluster_capacity_providers.this]

  tags = merge(local.common_tags, { Service = each.key })
}
