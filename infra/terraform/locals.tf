locals {
  name_prefix = "${var.project_name}-${var.environment}"

  service_names = [
    "gateway",
    "user",
    "orchestration",
    "speaking",
    "writing",
    "rag",
    "exam",
    "notification",
    "ingestion",
  ]

  postgres_databases = {
    user          = "user_db"
    orchestration = "orchestration_db"
    speaking      = "speaking_db"
    writing       = "writing_db"
    rag           = "rag_db"
    exam          = "exam_db"
    notification  = "notification_db"
    ingestion     = "ingestion_db"
  }

  redis_logical_databases = {
    gateway_rate_limits          = 0
    orchestration_session_memory = 1
  }

  sqs_queues = {
    user_events = {
      name                       = "user-events"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    notification = {
      name                       = "notification-queue"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    ingestion = {
      name                       = "ingestion-queue"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }
  }

  service_secret_keys = {
    gateway = [
      "JWT_SECRET",
    ]

    user = [
      "DATABASE_URL",
      "INTERNAL_API_KEY",
      "STRIPE_SECRET_KEY",
      "STRIPE_WEBHOOK_SECRET",
    ]

    orchestration = [
      "DATABASE_URL",
      "ANTHROPIC_API_KEY",
      "OPENAI_API_KEY",
      "INTERNAL_API_KEY",
    ]

    speaking = [
      "DATABASE_URL",
      "OPENAI_API_KEY",
      "ELEVENLABS_API_KEY",
      "INTERNAL_API_KEY",
    ]

    writing = [
      "DATABASE_URL",
      "ANTHROPIC_API_KEY",
      "LANGFUSE_PUBLIC_KEY",
      "LANGFUSE_SECRET_KEY",
      "LANGFUSE_HOST",
      "OPENAI_API_KEY",
      "INTERNAL_API_KEY",
    ]

    rag = [
      "DATABASE_URL",
      "ANTHROPIC_API_KEY",
    ]

    exam = [
      "DATABASE_URL",
      "INTERNAL_API_KEY",
    ]

    notification = [
      "DATABASE_URL",
      "INTERNAL_API_KEY",
    ]

    ingestion = [
      "DATABASE_URL",
      "INTERNAL_API_KEY",
    ]
  }

  rds_instance_classes = {
    staging    = "db.t3.micro"
    production = "db.t3.small"
  }

  redis_node_types = {
    staging    = "cache.t3.micro"
    production = "cache.t3.small"
  }

  rds_instance_class = lookup(local.rds_instance_classes, var.environment, "db.t3.micro")
  redis_node_type    = lookup(local.redis_node_types, var.environment, "cache.t3.micro")
  rds_multi_az       = var.environment == "production"

  ecs_service_names = {
    for service in local.service_names :
    service => lookup(var.goa069_ecs_service_names, service, "${local.name_prefix}-${service}")
  }

  service_sqs_queue_keys = {
    user = [
      "user_events",
    ]

    notification = [
      "notification",
    ]

    ingestion = [
      "ingestion",
    ]
  }

  service_sqs_queue_arns = {
    for service in local.service_names :
    service => [
      for queue_key in lookup(local.service_sqs_queue_keys, service, []) :
      module.sqs.queue_arns[queue_key]
    ]
  }

  service_secret_arns = {
    for service in local.service_names :
    service => try([module.secrets.service_secret_arns[service]], [])
  }

  goa027_alarm_definitions = merge(
    {
      speaking_p95_latency = {
        alarm_name          = "${local.name_prefix}-speaking-p95-latency"
        description         = "Speaking service P95 latency is above the GOA-027 threshold."
        namespace           = "GOA/Services"
        metric_name         = "LatencyMs"
        dimensions          = { Service = "speaking" }
        comparison_operator = "GreaterThanThreshold"
        threshold           = var.speaking_p95_latency_threshold_ms
        evaluation_periods  = 2
        datapoints_to_alarm = 2
        period              = 60
        extended_statistic  = "p95"
        treat_missing_data  = "notBreaching"
      }

      cv_processor_failure_queue_depth = {
        alarm_name          = "${local.name_prefix}-cv-processor-failure-queue-depth"
        description         = "CV processor asynchronous invocation failures are waiting for replay."
        namespace           = "AWS/SQS"
        metric_name         = "ApproximateNumberOfMessagesVisible"
        dimensions          = { QueueName = aws_sqs_queue.cv_processor_failures.name }
        comparison_operator = "GreaterThanOrEqualToThreshold"
        threshold           = 1
        evaluation_periods  = 1
        datapoints_to_alarm = 1
        period              = 60
        statistic           = "Maximum"
        treat_missing_data  = "notBreaching"
      }
    },
    {
      for service in local.service_names :
      "service_error_rate_${service}" => {
        alarm_name          = "${local.name_prefix}-${service}-error-rate"
        description         = "${service} service error rate is above the GOA-027 threshold."
        namespace           = "GOA/Services"
        metric_name         = "ErrorRate"
        dimensions          = { Service = service }
        comparison_operator = "GreaterThanThreshold"
        threshold           = var.service_error_rate_threshold
        evaluation_periods  = 2
        datapoints_to_alarm = 2
        period              = 60
        statistic           = "Average"
        treat_missing_data  = "notBreaching"
      }
    },
    {
      for queue_key, dlq_name in module.sqs.dlq_names :
      "dlq_depth_${queue_key}" => {
        alarm_name          = "${local.name_prefix}-${queue_key}-dlq-depth"
        description         = "${dlq_name} contains visible messages."
        namespace           = "AWS/SQS"
        metric_name         = "ApproximateNumberOfMessagesVisible"
        dimensions          = { QueueName = dlq_name }
        comparison_operator = "GreaterThanOrEqualToThreshold"
        threshold           = var.dlq_visible_messages_threshold
        evaluation_periods  = 1
        datapoints_to_alarm = 1
        period              = 60
        statistic           = "Maximum"
        treat_missing_data  = "notBreaching"
      }
    },
    {
      for service in local.service_names :
      "ecs_running_task_count_${service}" => {
        alarm_name          = "${local.name_prefix}-${service}-ecs-running-tasks"
        description         = "${service} ECS service running task count is below the GOA-027 threshold."
        namespace           = "ECS/ContainerInsights"
        metric_name         = "RunningTaskCount"
        dimensions          = { ClusterName = var.ecs_cluster_name, ServiceName = local.ecs_service_names[service] }
        comparison_operator = "LessThanThreshold"
        threshold           = var.ecs_running_task_minimum
        evaluation_periods  = 2
        datapoints_to_alarm = 2
        period              = 60
        statistic           = "Minimum"
        treat_missing_data  = "breaching"
      }
    }
  )

  common_tags = merge(
    var.tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  )
}
