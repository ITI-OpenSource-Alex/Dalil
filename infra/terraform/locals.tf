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
    "ingestion",
    "notification",
    # GOA-030. The IAM, observability and log-group maps are all built from this
    # list, so a service missing here has no execution role and no log group and
    # fails at plan time rather than at deploy.
    "speech",
    "embeddings",
  ]

  # GOA-030: `speech` and `embeddings` were missing, and their absence is why a
  # deployed environment could not serve its two most important flows.
  #
  # Both exist locally and neither was ever deployed:
  #
  #   speech      Speaking calls it for STT and defaults to "http://speech:8086"
  #               (internal/speaking/config.go). Nothing answered that name in
  #               AWS, so every transcription failed and the speaking flow
  #               produced nothing.
  #   embeddings  RAG embeds every query through an OpenAI-compatible endpoint
  #               and defaults to the developer's own Ollama on
  #               host.docker.internal. Unreachable from Fargate, so every
  #               /query and /match failed at the embedding call.
  #
  # `embeddings` runs Ollama serving nomic-embed-text deliberately, rather than
  # a hosted embedding API. The 3,979 chunks already in the catalogue were
  # embedded with that exact model at 768 dimensions; a different model produces
  # vectors that are not comparable to them, so switching providers would
  # silently turn every similarity score into noise unless the whole corpus were
  # re-embedded first.
  #
  # Neither is behind the ALB. They are internal sidecars reached over Service
  # Connect by their client alias, exactly like every other in-VPC hop.
  ecs_deployed_service_names = [
    "gateway",
    "user",
    "orchestration",
    "speaking",
    "writing",
    "rag",
    "exam",
    "ingestion",
    "speech",
    "embeddings",
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
    ingestion     = 0
    speech        = 8086
    embeddings    = 11434
  }

  service_task_sizes = {
    gateway       = { cpu = 256, memory = 512 }
    user          = { cpu = 256, memory = 512 }
    orchestration = { cpu = 512, memory = 1024 }
    speaking      = { cpu = 512, memory = 1024 }
    writing       = { cpu = 512, memory = 1024 }
    rag           = { cpu = 512, memory = 1024 }
    exam          = { cpu = 256, memory = 512 }
    ingestion     = { cpu = 1024, memory = 2048 }
    # faster-whisper is CPU-bound and the load test's speaking scenario is
    # entirely gated on it: slo.go records a transcription ratio of 0.34-0.48 of
    # audio duration on 2 vCPU locally, worst on SHORT utterances because the
    # per-call overhead is amortised over less audio.
    speech = { cpu = 2048, memory = 4096 }
    # Ollama holds the model in memory. nomic-embed-text is small (274MB of
    # weights) but the runtime needs headroom, and an OOM here presents as
    # every RAG query failing rather than as a memory problem.
    embeddings = { cpu = 1024, memory = 3072 }
  }

  # An explicit override wins; otherwise the in-VPC Ollama sidecar. Ollama
  # exposes an OpenAI-compatible API under /v1, which is what the RAG and
  # ingestion clients speak.
  effective_embedding_base_url = (
    var.rag_embedding_base_url != ""
    ? var.rag_embedding_base_url
    : "http://${local.name_prefix}-embeddings:11434/v1"
  )

  ecs_services = {
    for service in local.ecs_deployed_service_names : service => {
      image                             = "${module.ecr.repository_urls[service]}:${var.ecs_image_tag}"
      container_port                    = local.service_ports[service]
      cpu                               = local.service_task_sizes[service].cpu
      memory                            = local.service_task_sizes[service].memory
      desired_count                     = lookup(var.ecs_desired_counts, service, service == "ingestion" ? 0 : 1)
      health_check_grace_period_seconds = 120
      environment = merge({
        ENVIRONMENT = var.environment
        PORT        = tostring(local.service_ports[service])
        AWS_REGION  = var.aws_region
        # Every LLM-producing service writes the Gateway-owned daily cost roll-up.
        REDIS_GATEWAY_URL = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/0"
        }, service == "gateway" ? {
        PORT                      = "8080"
        REDIS_URL                 = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/0"
        WRITING_SERVICE_URL       = "http://${local.name_prefix}-writing:8000"
        EXAM_SERVICE_URL          = "http://${local.name_prefix}-exam:8085"
        USER_SERVICE_URL          = "http://${local.name_prefix}-user:8081"
        ORCHESTRATION_SERVICE_URL = "http://${local.name_prefix}-orchestration:8083"
        # GOA-030. Missing entirely, so the Gateway fell back to its compose
        # default of http://rag:8084, which resolves to nothing in the VPC.
        # Every /api/opportunities/* and /api/checklists/* call answered 502
        # "failed to contact opportunity search" -- with the real cause invisible,
        # because the handler reports a friendly message and not the dial error.
        RAG_SERVICE_URL      = "http://${local.name_prefix}-rag:8084"
        SPEAKING_SERVICE_URL = "http://${local.name_prefix}-speaking:8082"
        SECURE_COOKIES       = "true"
        INGESTION_QUEUE_URL  = module.sqs.queue_urls["ingestion"]
        } : service == "user" ? {
        REDIS_HOST            = module.elasticache.primary_endpoint_address
        REDIS_PORT            = tostring(module.elasticache.port)
        USER_EVENTS_TOPIC_ARN = aws_sns_topic.user_events.arn
        # GOA-030. RDS is signed by an Amazon CA that is not in Node's bundled
        # trust store, so the service crash-looped on SELF_SIGNED_CERT_IN_CHAIN
        # and the Gateway answered "no healthy upstream" for every auth route.
        #
        # NODE_EXTRA_CA_CERTS rather than the driver's own ssl option, because
        # DATABASE_URL carries an sslmode parameter: pg-connection-string builds
        # its TLS config from the URL and OVERRIDES anything passed
        # programmatically, so data-source.ts's `ssl: { ca }` never applied.
        # This augments Node's default trust store instead, which every code
        # path inherits.
        #
        # The bundle is baked into the image at this path by the user
        # Dockerfile; see the comment there.
        NODE_EXTRA_CA_CERTS = "/etc/ssl/certs/rds-global-bundle.pem"
        } : service == "orchestration" ? {
        REDIS_URL            = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/1"
        RAG_SERVICE_URL      = "http://${local.name_prefix}-rag:8084"
        SPEAKING_SERVICE_URL = "http://${local.name_prefix}-speaking:8082"
        WRITING_SERVICE_URL  = "http://${local.name_prefix}-writing:8000"
        SQS_QUEUE_NAME       = module.sqs.queue_names["user_events_orchestration"]
        } : service == "writing" ? {
        S3_BUCKET                 = module.writing_files_bucket.bucket_name
        CV_PROCESSED_QUEUE_URL    = aws_sqs_queue.cv_processed.url
        ACCOUNT_DELETED_QUEUE_URL = module.sqs.queue_urls["user_events_writing"]
        } : service == "rag" ? {
        REDIS_URL      = "redis://${module.elasticache.primary_endpoint_address}:${module.elasticache.port}/1"
        SQS_QUEUE_NAME = module.sqs.queue_names["user_events_rag"]
        # GOA-030. Without these, RAG falls back to its code default of
        # host.docker.internal:11434 -- the developer's own Ollama -- and every
        # /query and /match fails at the embedding call inside a Fargate task.
        # See the comment on rag_embedding_base_url in variables.tf.
        EMBEDDING_BASE_URL   = local.effective_embedding_base_url
        EMBEDDING_MODEL      = var.rag_embedding_model
        EMBEDDING_DIMENSIONS = tostring(var.rag_embedding_dimensions)
        } : service == "exam" ? {
        SPEAKING_SERVICE_URL = "http://${local.name_prefix}-speaking:8082"
        WRITING_SERVICE_URL  = "http://${local.name_prefix}-writing:8000"
        S3_BUCKET            = module.exam_audio_bucket.bucket_name
        SQS_QUEUE_NAME       = module.sqs.queue_names["user_events_exam"]
        } : service == "speaking" ? {
        SQS_QUEUE_NAME = module.sqs.queue_names["user_events_speaking"]
        # GOA-030. Without this Speaking uses its code default
        # "http://speech:8086", which resolves to nothing in the VPC, and every
        # transcription fails -- the swarm then grades an empty transcript.
        SPEECH_SERVICE_URL = "http://${local.name_prefix}-speech:8086"
        } : service == "ingestion" ? {
        RAG_SERVICE_URL                     = "http://${local.name_prefix}-rag:8084"
        INGESTION_QUEUE_URL                 = module.sqs.queue_urls["ingestion"]
        INGESTION_REPORTS_BUCKET            = module.ingestion_reports_bucket.bucket_name
        INGESTION_WALL_CLOCK_BUDGET_SECONDS = "3600"
        INGESTION_SAFETY_MARGIN_SECONDS     = "120"
        INGESTION_VISIBILITY_TIMEOUT        = "4320"
        EMBEDDING_BASE_URL                  = local.effective_embedding_base_url
        EMBEDDING_MODEL                     = var.rag_embedding_model
        EMBEDDING_DIMENSIONS                = tostring(var.rag_embedding_dimensions)
      } : {})
      secrets = module.secrets.service_secret_value_from_refs[service]
    }
  }

  ecs_migration_commands = {
    gateway       = ["sh", "-c", "echo 'gateway owns no database migrations'"]
    user          = ["sh", "-c", "if [ \"$MIGRATION_DIRECTION\" = \"down\" ]; then npm run migration:revert:prod; else npm run migration:run:prod; fi"]
    orchestration = ["python", "-m", "app.migrate"]
    speaking      = ["./speaking", "migrate"]
    writing       = ["python", "-m", "app.init_db"]
    rag           = ["python", "-m", "app.migrate"]
    exam          = ["python", "-m", "app.migrate"]
    ingestion     = ["python", "-m", "app.migrate"]
    # Neither sidecar owns a database. They still need an entry: the migration
    # task map is built from ecs_deployed_service_names, and a missing key is a
    # plan-time lookup error rather than a skipped migration.
    speech     = ["sh", "-c", "echo 'speech owns no database migrations'"]
    embeddings = ["sh", "-c", "echo 'embeddings owns no database migrations'"]
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
    notification = {
      name                       = "${local.name_prefix}-notification-queue"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    ingestion = {
      name                       = "${local.name_prefix}-ingestion-queue"
      visibility_timeout_seconds = 4320
      max_receive_count          = 3
    }

    user_events_rag = {
      name                       = "${local.name_prefix}-user-events-rag"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    user_events_orchestration = {
      name                       = "${local.name_prefix}-user-events-orchestration"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    user_events_exam = {
      name                       = "${local.name_prefix}-user-events-exam"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    user_events_speaking = {
      name                       = "${local.name_prefix}-user-events-speaking"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    user_events_writing = {
      name                       = "${local.name_prefix}-user-events-writing"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }

    user_events_notification = {
      name                       = "${local.name_prefix}-user-events-notification"
      visibility_timeout_seconds = 30
      max_receive_count          = 3
    }
  }

  user_event_subscriber_queue_keys = toset([
    "user_events_rag",
    "user_events_orchestration",
    "user_events_exam",
    "user_events_speaking",
    "user_events_writing",
    "user_events_notification",
  ])

  service_secret_keys = {
    gateway = [
      "JWT_SECRET",
      "INTERNAL_API_KEY",
      "ADMIN_API_KEY",
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

    # No OPENAI_API_KEY: GOA-093 consolidated Academic Task 1 vision onto Claude,
    # leaving the Writing service with no OpenAI call of any kind. OpenAI remains
    # only where embeddings are needed (RAG/Ingestion) or speech (Speaking).
    writing = [
      "DATABASE_URL",
      "ANTHROPIC_API_KEY",
      "LANGFUSE_PUBLIC_KEY",
      "LANGFUSE_SECRET_KEY",
      "LANGFUSE_HOST",
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
      "SES_SENDER_ADDRESS",
    ]

    ingestion = [
      "DATABASE_URL",
      "ANTHROPIC_API_KEY",
      "INTERNAL_API_KEY",
    ]

    # Neither sidecar holds a credential: speech transcribes bytes it is handed
    # and embeddings serves a local model. Empty lists rather than omitted keys,
    # because the secrets module iterates this map by service.
    speech     = []
    embeddings = []
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
    gateway = [
      "ingestion",
    ]

    speech     = []
    embeddings = []

    user = []

    rag = [
      "user_events_rag",
    ]

    orchestration = [
      "user_events_orchestration",
    ]

    exam = [
      "user_events_exam",
    ]

    speaking = [
      "user_events_speaking",
    ]

    writing = [
      "user_events_writing",
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

  service_sns_topic_arns = {
    for service in local.service_names :
    service => service == "user" ? [aws_sns_topic.user_events.arn] : []
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
    speech        = []
    embeddings    = []
    ingestion = [
      "${module.ingestion_reports_bucket.bucket_arn}/*",
      "${module.eval_reports_bucket.bucket_arn}/*",
    ]
  }

  service_s3_write_object_arns = {
    for service in local.service_names :
    service => service == "ingestion" ? [
      "${module.ingestion_reports_bucket.bucket_arn}/*",
    ] : []
  }

  ecs_iam_permissions = merge(
    {
      for service in local.service_names : service => {
        execution_secret_arns = toset(local.service_secret_arns[service])
        task_secret_arns      = toset(local.service_secret_arns[service])
        sqs_queue_arns        = toset(local.service_sqs_queue_arns[service])
        sns_topic_arns        = toset(local.service_sns_topic_arns[service])
        s3_read_object_arns   = toset(local.service_s3_read_object_arns[service])
        s3_write_object_arns  = toset(local.service_s3_write_object_arns[service])
        kms_key_arns          = toset(var.task_kms_key_arns)
      }
    },
    {
      db-bootstrap = {
        execution_secret_arns = toset([module.secrets.rds_master_secret_arn])
        task_secret_arns      = toset([])
        sqs_queue_arns        = toset([])
        sns_topic_arns        = toset([])
        s3_read_object_arns   = toset([])
        s3_write_object_arns  = toset([])
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
        treat_missing_data  = "missing"
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
      # GOA-066: Reading/Listening grading is pure code + DB (no LLM), so a P95
      # above 500ms points at a DB or code regression. One alarm per skill_area
      # because each is a distinct dimension value on goa_exam_grading_latency_ms.
      for skill in ["reading", "listening"] :
      "exam_grading_p95_${skill}" => {
        alarm_name          = "${local.name_prefix}-exam-${skill}-grading-p95-latency"
        description         = "Exam ${skill} grading latency P95 is above the GOA-066 500ms threshold — indicates a DB or code issue."
        namespace           = "GOA/Services"
        metric_name         = "goa_exam_grading_latency_ms"
        dimensions          = { Service = "exam", skill_area = skill }
        comparison_operator = "GreaterThanThreshold"
        threshold           = var.reading_listening_grading_p95_threshold_ms
        evaluation_periods  = 5
        datapoints_to_alarm = 5
        period              = 60
        extended_statistic  = "p95"
        treat_missing_data  = "missing"
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
        treat_missing_data  = "missing"
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
    },
    {
      ingestion_failure_ratio = {
        alarm_name          = "${local.name_prefix}-ingestion-failure-ratio"
        description         = "More than ten percent of the bounded ingestion batch failed."
        namespace           = "GOA/Ingestion"
        metric_name         = "FailureRate"
        dimensions          = { Environment = var.environment }
        comparison_operator = "GreaterThanThreshold"
        threshold           = 10
        evaluation_periods  = 1
        datapoints_to_alarm = 1
        period              = 60
        statistic           = "Maximum"
        treat_missing_data  = "notBreaching"
      }

      ingestion_stale_sources = {
        alarm_name          = "${local.name_prefix}-ingestion-stale-sources"
        description         = "No successful ingestion freshness heartbeat was emitted for a week."
        namespace           = "GOA/Ingestion"
        metric_name         = "FreshnessHeartbeat"
        dimensions          = { Environment = var.environment }
        comparison_operator = "LessThanThreshold"
        threshold           = 1
        evaluation_periods  = 1
        datapoints_to_alarm = 1
        period              = 604800
        statistic           = "Maximum"
        treat_missing_data  = "breaching"
      }

      weekly_ingestion_failed_schedule = {
        alarm_name          = "${local.name_prefix}-weekly-ingestion-failed-schedule"
        description         = "The weekly program ingestion EventBridge target failed."
        namespace           = "AWS/Events"
        metric_name         = "FailedInvocations"
        dimensions          = { RuleName = "goa-weekly-program-ingestion-${var.environment}" }
        comparison_operator = "GreaterThanOrEqualToThreshold"
        threshold           = 1
        evaluation_periods  = 1
        datapoints_to_alarm = 1
        period              = 60
        statistic           = "Sum"
        treat_missing_data  = "notBreaching"
      }

      monthly_visa_failed_schedule = {
        alarm_name          = "${local.name_prefix}-monthly-visa-failed-schedule"
        description         = "The monthly visa verification EventBridge target failed."
        namespace           = "AWS/Events"
        metric_name         = "FailedInvocations"
        dimensions          = { RuleName = "goa-monthly-visa-verification-${var.environment}" }
        comparison_operator = "GreaterThanOrEqualToThreshold"
        threshold           = 1
        evaluation_periods  = 1
        datapoints_to_alarm = 1
        period              = 60
        statistic           = "Sum"
        treat_missing_data  = "notBreaching"
      }
    }
  )

  # Cost attribution (GOA-046). Every resource carries a Service tag so Cost
  # Explorer can split spend per service. Resources with no single owning
  # service — VPC, NAT, ALB, RDS, Redis — are deliberately tagged "shared"
  # rather than left untagged, so an unattributed line in the cost report is a
  # real tagging gap rather than shared infrastructure that nobody labelled.
  common_tags = merge(
    var.tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Service     = "shared"
    }
  )
}
