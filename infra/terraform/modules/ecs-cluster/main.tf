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

resource "aws_service_discovery_http_namespace" "this" {
  name        = "${var.name_prefix}.local"
  description = "ECS Service Connect namespace for ${var.name_prefix}."
  tags        = local.common_tags
}

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  service_connect_defaults {
    namespace = aws_service_discovery_http_namespace.this.arn
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
