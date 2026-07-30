data "aws_region" "current" {}

locals {
  service_resource_name = "${var.name_prefix}-${var.service_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "ecs-service"
    Project     = "goa"
    Service     = var.service_name
  })
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.service_resource_name
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = var.service_name
    image     = var.image_uri
    essential = true
    portMappings = var.enable_load_balancer ? [{
      name          = var.service_name
      containerPort = var.container_port
      hostPort      = var.container_port
      protocol      = "tcp"
      appProtocol   = "http"
    }] : []
    environment = [
      for name, value in var.environment_variables : {
        name  = name
        value = value
      }
    ]
    secrets = [
      for name, value_from in var.secrets : {
        name      = name
        valueFrom = value_from
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = var.log_group_name
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = var.service_name
      }
    }
  }])

  tags = local.common_tags
}

resource "aws_ecs_service" "this" {
  name                   = local.service_resource_name
  cluster                = var.cluster_id
  task_definition        = aws_ecs_task_definition.this.arn
  desired_count          = var.desired_count
  enable_execute_command = true
  launch_type            = "FARGATE"
  propagate_tags         = "SERVICE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = var.health_check_grace_period_seconds

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = false
    subnets          = var.private_subnet_ids
    security_groups  = var.security_group_ids
  }

  dynamic "service_connect_configuration" {
    for_each = var.enable_service_connect ? [1] : []
    content {
      enabled   = true
      namespace = var.service_connect_namespace_arn

      dynamic "service" {
        for_each = var.advertise_service ? [1] : []
        content {
          port_name      = var.service_name
          discovery_name = var.service_name

          client_alias {
            dns_name = local.service_resource_name
            port     = var.container_port
          }
        }
      }
    }
  }

  dynamic "load_balancer" {
    for_each = var.enable_load_balancer ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.service_name
      container_port   = var.container_port
    }
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.common_tags
}

resource "aws_appautoscaling_target" "this" {
  max_capacity       = var.autoscaling_max_capacity
  min_capacity       = var.autoscaling_min_capacity
  resource_id        = "service/${var.cluster_name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${local.service_resource_name}-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${local.service_resource_name}-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 600
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  actions_enabled     = var.enable_utilization_autoscaling
  alarm_name          = "${local.service_resource_name}-cpu-high"
  alarm_description   = "Scale out when ECS CPU utilization reaches 70 percent."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = { ClusterName = var.cluster_name, ServiceName = aws_ecs_service.this.name }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 70
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  period              = 60
  statistic           = "Average"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.scale_out.arn]
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "memory_high" {
  actions_enabled     = var.enable_utilization_autoscaling
  alarm_name          = "${local.service_resource_name}-memory-high"
  alarm_description   = "Scale out when ECS memory utilization reaches 80 percent."
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  dimensions          = { ClusterName = var.cluster_name, ServiceName = aws_ecs_service.this.name }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 80
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  period              = 60
  statistic           = "Average"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.scale_out.arn]
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "capacity_low" {
  actions_enabled     = var.enable_utilization_autoscaling
  alarm_name          = "${local.service_resource_name}-capacity-low"
  alarm_description   = "Scale in when both ECS CPU and memory remain below 30 percent for 10 minutes."
  comparison_operator = "LessThanThreshold"
  threshold           = 30
  evaluation_periods  = 10
  datapoints_to_alarm = 10
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.scale_in.arn]
  tags                = local.common_tags

  metric_query {
    id          = "utilization"
    expression  = "MAX([cpu,memory])"
    label       = "Highest CPU or memory utilization"
    return_data = true
  }

  metric_query {
    id          = "cpu"
    return_data = false

    metric {
      namespace   = "AWS/ECS"
      metric_name = "CPUUtilization"
      dimensions  = { ClusterName = var.cluster_name, ServiceName = aws_ecs_service.this.name }
      period      = 60
      stat        = "Average"
    }
  }

  metric_query {
    id          = "memory"
    return_data = false

    metric {
      namespace   = "AWS/ECS"
      metric_name = "MemoryUtilization"
      dimensions  = { ClusterName = var.cluster_name, ServiceName = aws_ecs_service.this.name }
      period      = 60
      stat        = "Average"
    }
  }
}
