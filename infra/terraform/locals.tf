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

  ecs_deployed_service_names = [
    "gateway",
    "user",
    "orchestration",
    "speaking",
    "writing",
    "rag",
    "exam",
  ]

  lambda_worker_names = [
    "cv-processor",
    "scholarship-matcher",
    "notification-sender",
  ]

  ecr_repository_names = concat(local.ecs_deployed_service_names, local.lambda_worker_names)

  service_ports = {
    gateway       = 8080
    user          = 8081
    orchestration = 8083
    speaking      = 8082
    writing       = 8000
    rag           = 8084
    exam          = 8085
  }

  service_task_sizes = {
    gateway       = { cpu = 256, memory = 512 }
    user          = { cpu = 256, memory = 512 }
    orchestration = { cpu = 512, memory = 1024 }
    speaking      = { cpu = 512, memory = 1024 }
    writing       = { cpu = 512, memory = 1024 }
    rag           = { cpu = 512, memory = 1024 }
    exam          = { cpu = 256, memory = 512 }
  }

  ecs_services = {
    for service in local.ecs_deployed_service_names : service => {
      image                             = "${module.ecr.repository_urls[service]}:${var.ecs_image_tag}"
      container_port                    = local.service_ports[service]
      cpu                               = local.service_task_sizes[service].cpu
      memory                            = local.service_task_sizes[service].memory
      desired_count                     = lookup(var.ecs_desired_counts, service, 1)
      health_check_grace_period_seconds = 120
      environment = merge({
        ENVIRONMENT = var.environment
        PORT        = tostring(local.service_ports[service])
        AWS_REGION  = var.aws_region
        }, service == "gateway" ? {
        PORT                      = "8080"
        REDIS_URL                 = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/0"
        WRITING_SERVICE_URL       = "http://${local.name_prefix}-writing:8000"
        EXAM_SERVICE_URL          = "http://${local.name_prefix}-exam:8085"
        USER_SERVICE_URL          = "http://${local.name_prefix}-user:8081"
        ORCHESTRATION_SERVICE_URL = "http://${local.name_prefix}-orchestration:8083"
        SECURE_COOKIES            = "true"
        } : service == "user" ? {
        REDIS_HOST    = module.elasticache.primary_endpoint_address
        REDIS_PORT    = tostring(module.elasticache.port)
        SQS_QUEUE_URL = module.sqs.queue_urls["user_events"]
        } : service == "orchestration" ? {
        REDIS_URL            = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/1"
        RAG_SERVICE_URL      = "http://${local.name_prefix}-rag:8084"
        SPEAKING_SERVICE_URL = "http://${local.name_prefix}-speaking:8082"
        WRITING_SERVICE_URL  = "http://${local.name_prefix}-writing:8000"
        } : service == "writing" ? {
        S3_BUCKET              = module.writing_files_bucket.bucket_name
        CV_PROCESSED_QUEUE_URL = aws_sqs_queue.cv_processed.url
        } : service == "rag" ? {
        REDIS_URL      = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/1"
        SQS_QUEUE_NAME = module.sqs.queue_names["user_events"]
        } : service == "exam" ? {
        SPEAKING_SERVICE_URL = "http://${local.name_prefix}-speaking:8082"
        WRITING_SERVICE_URL  = "http://${local.name_prefix}-writing:8000"
        S3_BUCKET            = module.exam_audio_bucket.bucket_name
      } : {})
      secrets = module.secrets.service_secret_value_from_refs[service]
    }
  }

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
      name                       = "${local.name_prefix}-user-events"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    notification = {
      name                       = "${local.name_prefix}-notification-queue"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    ingestion = {
      name                       = "${local.name_prefix}-ingestion-queue"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }
  }

  service_secret_keys = {
    gateway = [
      "JWT_SECRET",
      "INTERNAL_API_KEY",
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

  ecs_service_resource_names = {
    for service in local.ecs_deployed_service_names :
    service => lookup(var.goa069_ecs_service_names, service, "${local.name_prefix}-${service}")
  }

  service_sqs_queue_keys = {
    user = [
      "user_events",
    ]

    rag = [
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

  service_s3_read_object_arns = {
    gateway       = []
    user          = []
    orchestration = []
    speaking      = []
    writing       = ["${module.writing_files_bucket.bucket_arn}/*"]
    rag           = []
    exam          = ["${module.exam_audio_bucket.bucket_arn}/exam-audio/*"]
    notification  = []
    ingestion = [
      "${module.ingestion_reports_bucket.bucket_arn}/*",
      "${module.eval_reports_bucket.bucket_arn}/*",
    ]
  }

  ecs_iam_permissions = merge(
    {
      for service in local.service_names : service => {
        execution_secret_arns = toset(local.service_secret_arns[service])
        task_secret_arns      = toset(local.service_secret_arns[service])
        sqs_queue_arns        = toset(local.service_sqs_queue_arns[service])
        s3_read_object_arns   = toset(local.service_s3_read_object_arns[service])
        kms_key_arns          = toset(var.task_kms_key_arns)
      }
    },
    {
      db-bootstrap = {
        execution_secret_arns = toset([module.secrets.rds_master_secret_arn])
        task_secret_arns      = toset([])
        sqs_queue_arns        = toset([])
        s3_read_object_arns   = toset([])
        kms_key_arns          = toset(var.task_kms_key_arns)
      }
    }
  )

  goa027_alarm_definitions = merge(
    {
      speaking_p95_latency = {
        alarm_name          = "${local.name_prefix}-speaking-p95-latency"
        description         = "Speaking service P95 latency is above the GOA-027 threshold."
        namespace           = "GOA/Services"
        metric_name         = "goa_speaking_e2e_latency_ms"
        dimensions          = { Service = "speaking" }
        comparison_operator = "GreaterThanThreshold"
        threshold           = var.speaking_p95_latency_threshold_ms
        evaluation_periods  = 5
        datapoints_to_alarm = 5
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
        evaluation_periods  = 5
        datapoints_to_alarm = 5
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
      for service in local.ecs_deployed_service_names :
      "ecs_running_task_count_${service}" => {
        alarm_name          = "${local.name_prefix}-${service}-ecs-running-tasks"
        description         = "${service} ECS service running task count is below the GOA-027 threshold."
        namespace           = "ECS/ContainerInsights"
        metric_name         = "RunningTaskCount"
        dimensions          = { ClusterName = local.name_prefix, ServiceName = local.ecs_service_resource_names[service] }
        comparison_operator = "LessThanThreshold"
        threshold           = lookup(var.ecs_desired_counts, service, 0)
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
