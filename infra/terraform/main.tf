module "vpc" {
  source = "./modules/vpc"

  environment               = var.environment
  vpc_cidr                  = var.vpc_cidr
  availability_zones        = var.availability_zones
  public_subnet_cidrs       = var.public_subnet_cidrs
  private_app_subnet_cidrs  = var.private_app_subnet_cidrs
  private_data_subnet_cidrs = var.private_data_subnet_cidrs
  tags                      = var.tags
}

module "nat_gateway" {
  source = "./modules/nat-gateway"

  environment                  = var.environment
  public_subnet_ids            = module.vpc.public_subnet_ids
  private_app_route_table_ids  = module.vpc.private_app_route_table_ids
  private_data_route_table_ids = module.vpc.private_data_route_table_ids
  tags                         = var.tags

  depends_on = [module.vpc]
}

module "security_groups" {
  source = "./modules/security-groups"

  environment  = var.environment
  vpc_id       = module.vpc.vpc_id
  gateway_port = local.service_ports.gateway
  ecs_service_ports = [
    for service, port in local.service_ports : port
    if service != "gateway" && port > 0
  ]
  alb_direct_service_ports = [
    for service, port in local.service_ports : port
    if service != "gateway" && port > 0
  ]
  tags = var.tags
}

module "vpc_endpoints" {
  source = "./modules/vpc-endpoints"

  environment                   = var.environment
  aws_region                    = var.aws_region
  vpc_id                        = module.vpc.vpc_id
  interface_endpoint_subnet_ids = module.vpc.private_app_subnet_ids
  s3_route_table_ids            = concat(module.vpc.private_app_route_table_ids, module.vpc.private_data_route_table_ids)
  allowed_security_group_ids = [
    module.security_groups.gateway_security_group_id,
    module.security_groups.ecs_services_security_group_id,
  ]
  tags = var.tags
}

module "nonproduction_alb_certificate" {
  count  = var.create_self_signed_alb_certificate ? 1 : 0
  source = "./modules/acm"

  name_prefix = local.name_prefix
  domain_name = coalesce(var.domain_name, "${var.environment}.goa.internal")
  tags        = local.common_tags
}

module "production_dns_zone" {
  count  = var.enable_public_dns ? 1 : 0
  source = "./modules/route53"

  enabled          = true
  zone_name        = var.domain_name
  create_zone      = var.create_public_hosted_zone
  existing_zone_id = var.hosted_zone_id
  tags             = local.common_tags
}

module "production_alb_certificate" {
  count  = var.enable_public_dns ? 1 : 0
  source = "./modules/acm"

  name_prefix               = local.name_prefix
  certificate_type          = "public_dns"
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  route53_zone_id           = module.production_dns_zone[0].zone_id
  tags                      = local.common_tags
}

module "production_cloudfront_certificate" {
  count  = var.enable_public_dns ? 1 : 0
  source = "./modules/acm"

  providers = {
    aws = aws.us_east_1
  }

  name_prefix               = local.name_prefix
  certificate_type          = "public_dns"
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  route53_zone_id           = module.production_dns_zone[0].zone_id
  tags                      = local.common_tags
}

locals {
  effective_alb_certificate_arn = (
    var.create_self_signed_alb_certificate
    ? module.nonproduction_alb_certificate[0].certificate_arn
    : var.enable_public_dns
    ? module.production_alb_certificate[0].certificate_arn
    : var.alb_certificate_arn
  )
}

module "alb" {
  source = "./modules/alb"

  environment                = var.environment
  vpc_id                     = module.vpc.vpc_id
  public_subnet_ids          = module.vpc.public_subnet_ids
  alb_security_group_id      = module.security_groups.alb_security_group_id
  certificate_arn            = local.effective_alb_certificate_arn
  enable_deletion_protection = var.alb_enable_deletion_protection
  default_target_group_name  = var.alb_default_target_group_name
  target_groups              = var.alb_target_groups
  listener_rules = {
    speaking_websocket = {
      priority          = 10
      path_patterns     = ["/api/speaking/ws", "/api/speaking/ws/*"]
      target_group_name = "speaking"
    }
    exam = {
      priority          = 20
      path_patterns     = ["/api/exam/*"]
      target_group_name = "exam"
    }
    gateway_api = {
      priority          = 100
      path_patterns     = ["/api/*"]
      target_group_name = "gateway"
    }
  }
  tags = var.tags
}

module "production_api_dns" {
  count  = var.enable_public_dns ? 1 : 0
  source = "./modules/route53"

  enabled            = true
  zone_name          = var.domain_name
  create_zone        = false
  existing_zone_id   = module.production_dns_zone[0].zone_id
  create_api_alias   = true
  api_alias_dns_name = module.alb.alb_dns_name
  api_alias_zone_id  = module.alb.alb_zone_id
  tags               = local.common_tags
}

module "alb_waf" {
  count  = var.enable_public_dns ? 1 : 0
  source = "./modules/waf"

  name_prefix              = local.name_prefix
  scope                    = "REGIONAL"
  association_resource_arn = module.alb.alb_arn
  log_group_name           = "aws-waf-logs-goa-alb"
  rate_limit               = var.waf_rate_limit
  log_retention_days       = 30
  tags                     = local.common_tags
}

module "frontend_assets" {
  count  = var.enable_cloudfront ? 1 : 0
  source = "./modules/s3"

  bucket_name = coalesce(
    var.frontend_bucket_name,
    "${var.project_name}-${var.aws_account_id}-${var.environment}-frontend-assets"
  )
  force_destroy = false
  tags          = merge(local.common_tags, { Purpose = "frontend-assets" })
}

module "cloudfront_waf" {
  count  = var.enable_cloudfront ? 1 : 0
  source = "./modules/waf"

  providers = {
    aws = aws.us_east_1
  }

  name_prefix        = local.name_prefix
  scope              = "CLOUDFRONT"
  log_group_name     = "aws-waf-logs-goa-cloudfront"
  rate_limit         = var.waf_rate_limit
  log_retention_days = 30
  tags               = local.common_tags
}

module "cloudfront" {
  source = "./modules/cloudfront"

  enabled                 = var.enable_cloudfront
  name_prefix             = local.name_prefix
  s3_bucket_name          = try(module.frontend_assets[0].bucket_name, null)
  s3_bucket_arn           = try(module.frontend_assets[0].bucket_arn, null)
  s3_regional_domain_name = try(module.frontend_assets[0].bucket_regional_domain_name, null)
  alb_origin_domain_name  = var.enable_public_dns ? "api.${var.domain_name}" : module.alb.alb_dns_name
  origin_protocol_policy  = "https-only"
  aliases                 = var.enable_public_dns ? [var.domain_name] : []
  acm_certificate_arn     = try(module.production_cloudfront_certificate[0].certificate_arn, null)
  web_acl_arn             = try(module.cloudfront_waf[0].web_acl_arn, null)
  price_class             = var.cloudfront_price_class
  tags                    = local.common_tags

  depends_on = [module.production_api_dns]
}

module "production_frontend_dns" {
  count  = var.enable_public_dns && var.enable_cloudfront ? 1 : 0
  source = "./modules/route53"

  enabled             = true
  zone_name           = var.domain_name
  create_zone         = false
  existing_zone_id    = module.production_dns_zone[0].zone_id
  create_root_alias   = true
  root_alias_dns_name = module.cloudfront.domain_name
  root_alias_zone_id  = module.cloudfront.hosted_zone_id
  tags                = local.common_tags
}

module "iam" {
  source = "./modules/iam"

  environment                        = var.environment
  ecs_service_permissions            = local.ecs_iam_permissions
  ecs_exec_operator_resource_arns    = var.ecs_exec_operator_resource_arns
  session_manager_log_retention_days = var.session_manager_log_retention_days
  session_manager_kms_key_id         = var.session_manager_kms_key_id
  manage_session_manager_preferences = var.manage_session_manager_preferences
  lambda_secret_arns                 = concat(var.lambda_secret_arns, values(module.secrets.service_secret_arns))
  lambda_sqs_queue_arns              = concat(var.sqs_notification_queue_arn != null ? [var.sqs_notification_queue_arn] : [], values(module.sqs.queue_arns), [aws_sqs_queue.cv_processed.arn, aws_sqs_queue.cv_processor_failures.arn])
  lambda_s3_bucket_arns              = [module.writing_files_bucket.bucket_arn]
  tags                               = var.tags
}

module "ecr" {
  source = "./modules/ecr"

  name_prefix           = local.name_prefix
  repositories          = toset(local.ecr_repository_names)
  image_retention_count = 10
  tags                  = local.common_tags
}

module "ecs_cluster" {
  source = "./modules/ecs-cluster"

  environment = var.environment
  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "ecs_service" {
  for_each = local.ecs_services
  source   = "./modules/ecs-service"

  environment                   = var.environment
  name_prefix                   = local.name_prefix
  cluster_id                    = module.ecs_cluster.cluster_id
  cluster_name                  = module.ecs_cluster.cluster_name
  service_connect_namespace_arn = module.ecs_cluster.service_connect_namespace_arn
  service_name                  = each.key
  image_uri                     = each.value.image
  cpu                           = each.value.cpu
  memory                        = each.value.memory
  desired_count                 = each.value.desired_count
  container_port                = each.value.container_port
  environment_variables         = each.value.environment
  secrets                       = each.value.secrets
  private_subnet_ids            = module.vpc.private_app_subnet_ids
  security_group_ids            = [each.key == "gateway" ? module.security_groups.gateway_security_group_id : module.security_groups.ecs_services_security_group_id]
  task_execution_role_arn       = module.iam.ecs_task_execution_role_arns[each.key]
  task_role_arn                 = module.iam.ecs_task_role_arns[each.key]
  target_group_arn              = try(module.alb.target_group_arns[each.key], null)
  # GOA-030: derived from the target-group map rather than by naming the one
  # service that opts out. `each.key != "ingestion"` was correct while ingestion
  # was the only service without a target group; the speech and embeddings
  # sidecars are also internal-only, and the old form would have attached them
  # to a load balancer with a null target group ARN.
  enable_load_balancer   = contains(keys(var.alb_target_groups), each.key)
  enable_service_connect = true
  # Still advertised over Service Connect even without an ALB -- that is exactly
  # how RAG reaches embeddings and Speaking reaches speech. Only ingestion, which
  # listens on no port at all, stays unadvertised.
  advertise_service                 = local.service_ports[each.key] > 0
  health_check_grace_period_seconds = each.key == "ingestion" ? 0 : each.value.health_check_grace_period_seconds
  log_group_name                    = module.observability.log_group_names[each.key]
  autoscaling_min_capacity          = each.key == "ingestion" ? 0 : 1
  autoscaling_max_capacity          = var.environment == "production" ? 10 : 4
  enable_utilization_autoscaling    = each.key != "ingestion"
  tags                              = local.common_tags
}

data "aws_region" "current" {}

data "aws_partition" "current" {}

locals {
  goa071_tags = merge(var.tags, {
    Ticket = "GOA-071"
  })

  cv_upload_prefix          = "cvs/"
  lambda_insights_layer_arn = "arn:${data.aws_partition.current.partition}:lambda:${data.aws_region.current.name}:580247275435:layer:LambdaInsightsExtension:14"
}

resource "aws_sqs_queue" "cv_processed_dlq" {
  name                      = "goa-cv-processed-${var.environment}-dlq"
  message_retention_seconds = 1209600
  tags                      = local.goa071_tags
}

resource "aws_sqs_queue" "cv_processed" {
  name                       = "goa-cv-processed-${var.environment}"
  visibility_timeout_seconds = 30
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.cv_processed_dlq.arn
    maxReceiveCount     = 3
  })
  tags = local.goa071_tags
}

resource "aws_sqs_queue" "cv_processor_failures" {
  name                      = "goa-cv-processor-failures-${var.environment}"
  message_retention_seconds = 1209600
  tags = merge(local.goa071_tags, {
    Purpose = "cv-processor-invocation-failures"
  })
}

# ---------------------------------------------------------------------------
# S3 buckets
# ---------------------------------------------------------------------------

module "writing_files_bucket" {
  source      = "./modules/s3"
  bucket_name = "goa-writing-files-${var.environment}"
  tags        = local.goa071_tags

  expiration_rules = [
    {
      id   = "expire-writing-files-retention-90d"
      days = 90
      tags = {
        retention = "90d"
      }
    }
  ]
}

module "exam_audio_bucket" {
  source      = "./modules/s3"
  bucket_name = "goa-exam-audio-${var.environment}"
  tags        = local.goa071_tags
}

module "ingestion_reports_bucket" {
  source      = "./modules/s3"
  bucket_name = "goa-ingestion-reports-${var.environment}"
  tags        = local.goa071_tags
}

module "eval_reports_bucket" {
  source      = "./modules/s3"
  bucket_name = "goa-eval-reports-${var.environment}"
  tags        = local.goa071_tags
}

# ---------------------------------------------------------------------------
# Lambda workers
# ---------------------------------------------------------------------------

module "cv_processor_lambda" {
  count             = var.enable_lambda_workers ? 1 : 0
  source            = "./modules/lambda"
  function_name     = "goa-cv-processor-${var.environment}"
  package_type      = "Image"
  image_uri         = "${module.ecr.repository_urls["cv-processor"]}:${var.image_tag}"
  image_entry_point = ["python", "-m", "awslambdaric"]
  image_command     = ["cv_processor.handler.lambda_handler"]

  role_arn                       = module.iam.lambda_execution_role_arn
  vpc_subnet_ids                 = module.vpc.private_app_subnet_ids
  vpc_security_group_ids         = [module.security_groups.lambda_security_group_id]
  timeout                        = 120
  memory_size                    = 1024
  reserved_concurrent_executions = 20
  lambda_insights_layer_arn      = local.lambda_insights_layer_arn

  environment_variables = {
    ENVIRONMENT            = var.environment
    WORKER                 = "cv-processor"
    S3_BUCKET              = module.writing_files_bucket.bucket_id
    CV_PROCESSED_QUEUE_URL = aws_sqs_queue.cv_processed.url
    CV_EXTRACTION_MODEL    = "claude-opus-5"
    # GOA-030: was "25". .env.example has warned since GOA-014 that a single
    # criterion agent regularly needs 40-90s and that 25s loses agents to
    # APITimeoutError. The same value was corrected in
    # services/writing/app/config.py after a 180-word essay returned
    # "1 of 4 writing agents failed: Request timed out". This copy is the one
    # that ships to every deployed environment, so leaving it at 25 would
    # reintroduce the defect the code fix just removed.
    ANTHROPIC_TIMEOUT_SECONDS = "120"
    WRITING_SECRET_ARN        = module.secrets.service_secret_arns["writing"]
  }

  tags = local.goa071_tags
}

resource "aws_cloudwatch_log_group" "cv_processor" {
  count             = var.enable_lambda_workers ? 1 : 0
  name              = "/aws/lambda/${module.cv_processor_lambda[0].function_name}"
  retention_in_days = 30
  tags = merge(local.goa071_tags, {
    Purpose = "cv-processor-runtime-logs"
  })
}

resource "aws_lambda_function_event_invoke_config" "cv_processor" {
  count                        = var.enable_lambda_workers ? 1 : 0
  function_name                = module.cv_processor_lambda[0].function_name
  maximum_event_age_in_seconds = 21600
  maximum_retry_attempts       = 2

  destination_config {
    on_failure {
      destination = aws_sqs_queue.cv_processor_failures.arn
    }
  }
}

module "scholarship_matcher_lambda" {
  count             = var.enable_lambda_workers ? 1 : 0
  source            = "./modules/lambda"
  function_name     = "goa-scholarship-matcher-${var.environment}"
  package_type      = "Image"
  image_uri         = "${module.ecr.repository_urls["scholarship-matcher"]}:${var.image_tag}"
  image_entry_point = ["python", "-m", "awslambdaric"]
  image_command     = ["app.workers.scholarship_matcher.handler"]

  role_arn                       = module.iam.lambda_execution_role_arn
  vpc_subnet_ids                 = module.vpc.private_app_subnet_ids
  vpc_security_group_ids         = [module.security_groups.lambda_security_group_id]
  timeout                        = 300
  memory_size                    = 1024
  reserved_concurrent_executions = 5
  lambda_insights_layer_arn      = local.lambda_insights_layer_arn

  environment_variables = {
    ENVIRONMENT            = var.environment
    WORKER                 = "scholarship-matcher"
    INGESTION_SECRET_ARN   = module.secrets.service_secret_arns["ingestion"]
    RAG_SERVICE_URL        = "http://${local.name_prefix}-rag:8084"
    NOTIFICATION_QUEUE_URL = module.sqs.queue_urls["notification"]
  }

  tags = local.goa071_tags
}

module "notification_sender_lambda" {
  count         = var.enable_lambda_workers ? 1 : 0
  source        = "./modules/lambda"
  function_name = "goa-notification-sender-${var.environment}"
  package_type  = "Image"
  image_uri     = "${module.ecr.repository_urls["notification-sender"]}:${var.image_tag}"

  role_arn                       = module.iam.lambda_execution_role_arn
  vpc_subnet_ids                 = module.vpc.private_app_subnet_ids
  vpc_security_group_ids         = [module.security_groups.lambda_security_group_id]
  timeout                        = 30
  memory_size                    = 512
  reserved_concurrent_executions = 50
  lambda_insights_layer_arn      = local.lambda_insights_layer_arn

  environment_variables = merge(
    {
      ENVIRONMENT             = var.environment
      WORKER                  = "notification-sender"
      NOTIFICATION_SECRET_ARN = module.secrets.service_secret_arns["notification"]
    },
    { SQS_QUEUE_URL = module.sqs.queue_urls["notification"] }
  )

  tags = local.goa071_tags
}

# ---------------------------------------------------------------------------
# EventBridge cron rules
# ---------------------------------------------------------------------------

module "weekly_program_ingestion_rule" {
  source              = "./modules/eventbridge"
  rule_name           = "goa-weekly-program-ingestion-${var.environment}"
  description         = "Queue a bounded weekly Tier 1 MastersPortal catalog sweep"
  schedule_expression = var.weekly_program_ingestion_schedule
  target_type         = "sqs"
  target_function_arn = module.sqs.queue_arns["ingestion"]
  input = jsonencode({
    tier        = 1
    adapters    = ["masters_portal"]
    max_items   = 500
    max_seconds = 3600
  })
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 7200
  dlq_arn                      = module.sqs.dlq_arns["ingestion"]
  tags                         = local.goa071_tags
}

module "monthly_visa_ingestion_rule" {
  source              = "./modules/eventbridge"
  rule_name           = "goa-monthly-visa-verification-${var.environment}"
  description         = "Queue monthly content-hash verification for configured visa sources"
  schedule_expression = var.monthly_visa_ingestion_schedule
  target_type         = "sqs"
  target_function_arn = module.sqs.queue_arns["ingestion"]
  input = jsonencode({
    tier        = 2
    adapters    = ["visa_adapter"]
    max_items   = 100
    max_seconds = 3600
  })
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 7200
  dlq_arn                      = module.sqs.dlq_arns["ingestion"]
  tags                         = local.goa071_tags
}

data "aws_iam_policy_document" "eventbridge_ingestion_queue" {
  statement {
    sid       = "AllowScheduledIngestion"
    actions   = ["sqs:SendMessage"]
    resources = [module.sqs.queue_arns["ingestion"]]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values = [
        module.weekly_program_ingestion_rule.rule_arn,
        module.monthly_visa_ingestion_rule.rule_arn,
      ]
    }
  }
}

resource "aws_sqs_queue_policy" "eventbridge_ingestion" {
  queue_url = module.sqs.queue_urls["ingestion"]
  policy    = data.aws_iam_policy_document.eventbridge_ingestion_queue.json
}

data "aws_iam_policy_document" "eventbridge_ingestion_dlq" {
  statement {
    sid       = "AllowFailedScheduledIngestion"
    actions   = ["sqs:SendMessage"]
    resources = [module.sqs.dlq_arns["ingestion"]]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values = [
        module.weekly_program_ingestion_rule.rule_arn,
        module.monthly_visa_ingestion_rule.rule_arn,
      ]
    }
  }
}

resource "aws_sqs_queue_policy" "eventbridge_ingestion_dlq" {
  queue_url = module.sqs.dlq_urls["ingestion"]
  policy    = data.aws_iam_policy_document.eventbridge_ingestion_dlq.json
}

module "daily_scholarship_match_rule" {
  count                = var.enable_lambda_workers ? 1 : 0
  source               = "./modules/eventbridge"
  rule_name            = "goa-daily-scholarship-match-${var.environment}"
  description          = "Daily scholarship matching run — 08:00 UTC"
  schedule_expression  = "cron(0 8 * * ? *)"
  target_function_name = module.scholarship_matcher_lambda[0].function_name
  target_function_arn  = module.scholarship_matcher_lambda[0].function_arn
  tags                 = local.goa071_tags
}

resource "aws_appautoscaling_policy" "ingestion_queue_scale_out" {
  name               = "${local.name_prefix}-ingestion-queue-scale-out"
  policy_type        = "StepScaling"
  resource_id        = module.ecs_service["ingestion"].autoscaling_resource_id
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  step_scaling_policy_configuration {
    adjustment_type = "ChangeInCapacity"
    cooldown        = 30
    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "ingestion_queue_scale_in" {
  name               = "${local.name_prefix}-ingestion-queue-scale-in"
  policy_type        = "StepScaling"
  resource_id        = module.ecs_service["ingestion"].autoscaling_resource_id
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  step_scaling_policy_configuration {
    adjustment_type = "ChangeInCapacity"
    cooldown        = 300
    step_adjustment {
      metric_interval_upper_bound = 1
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "ingestion_queue_has_work" {
  alarm_name          = "${local.name_prefix}-ingestion-queue-has-work"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = module.sqs.queue_names["ingestion"] }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.ingestion_queue_scale_out.arn]
}

resource "aws_cloudwatch_metric_alarm" "ingestion_queue_empty" {
  alarm_name          = "${local.name_prefix}-ingestion-queue-empty"
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 5
  datapoints_to_alarm = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.ingestion_queue_scale_in.arn]

  metric_query {
    id          = "backlog"
    expression  = "visible + inflight"
    label       = "Visible and in-flight ingestion jobs"
    return_data = true
  }

  metric_query {
    id          = "visible"
    return_data = false
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesVisible"
      dimensions  = { QueueName = module.sqs.queue_names["ingestion"] }
      period      = 60
      stat        = "Maximum"
    }
  }

  metric_query {
    id          = "inflight"
    return_data = false
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesNotVisible"
      dimensions  = { QueueName = module.sqs.queue_names["ingestion"] }
      period      = 60
      stat        = "Maximum"
    }
  }
}

# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------

resource "aws_lambda_permission" "s3_invoke_cv_processor" {
  count          = var.enable_lambda_workers ? 1 : 0
  statement_id   = "AllowExecutionFromS3WritingFiles"
  action         = "lambda:InvokeFunction"
  function_name  = module.cv_processor_lambda[0].function_name
  principal      = "s3.amazonaws.com"
  source_arn     = module.writing_files_bucket.bucket_arn
  source_account = var.aws_account_id
}

resource "aws_s3_bucket_notification" "writing_files" {
  count  = var.enable_lambda_workers ? 1 : 0
  bucket = module.writing_files_bucket.bucket_id

  lambda_function {
    lambda_function_arn = module.cv_processor_lambda[0].function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.cv_upload_prefix
  }

  depends_on = [aws_lambda_permission.s3_invoke_cv_processor]
}

# Skipped entirely until modules/sqs exists and sqs_notification_queue_arn
# is set — this whole resource is conditionally created via count.
resource "aws_lambda_event_source_mapping" "sqs_to_notification_sender" {
  count = var.enable_lambda_workers ? 1 : 0

  event_source_arn                   = module.sqs.queue_arns["notification"]
  function_name                      = module.notification_sender_lambda[0].function_name
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "account_deleted_to_notification_sender" {
  count = var.enable_lambda_workers ? 1 : 0

  event_source_arn                   = module.sqs.queue_arns["user_events_notification"]
  function_name                      = module.notification_sender_lambda[0].function_name
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

# CVProcessed is published by the Writing service to its own queue, not to
# notification-queue, so the notification Lambda needs a second source. Without
# this mapping the CV_PROCESSED notification type can never fire, and
# goa-cv-processed stays the write-only queue recorded in BUG-025.
#
# The ARN is aws_sqs_queue.cv_processed (declared above at ~line 151), NOT a
# module.sqs.queue_arns[...] lookup. module.sqs only holds user_events,
# notification and ingestion; the CV queues are declared directly in this file.
# An earlier version of this block used module.sqs.queue_arns["user_events"],
# which subscribed the Lambda to user-events instead: CV notifications still
# never fired, and every UserUpdated event became an unparseable message that
# retried three times and landed in user-events-dlq — poisoning the queue that
# feeds RAG's profile snapshot.
resource "aws_lambda_event_source_mapping" "cv_processed_to_notification_sender" {
  count = var.enable_lambda_workers ? 1 : 0

  event_source_arn                   = aws_sqs_queue.cv_processed.arn
  function_name                      = module.notification_sender_lambda[0].function_name
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

# ---------------------------------------------------------------------------
# Lambda alarms
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "lambda_error_rate" {
  for_each = var.enable_lambda_workers ? {
    cv_processor        = module.cv_processor_lambda[0].function_name
    scholarship_matcher = module.scholarship_matcher_lambda[0].function_name
    notification_sender = module.notification_sender_lambda[0].function_name
  } : {}

  alarm_name          = "${local.name_prefix}-${each.key}-lambda-error-rate"
  alarm_description   = "${each.key} Lambda error rate is above 5% over 15 minutes."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 15
  datapoints_to_alarm = 15
  treat_missing_data  = "notBreaching"
  alarm_actions       = [module.observability.sns_topic_arn]
  ok_actions          = [module.observability.sns_topic_arn]

  metric_query {
    id          = "errors"
    return_data = false
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = each.value }
      period      = 60
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "invocations"
    return_data = false
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Invocations"
      dimensions  = { FunctionName = each.value }
      period      = 60
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "error_rate"
    label       = "Lambda error rate (%)"
    expression  = "IF(invocations > 0, 100 * errors / invocations, 0)"
    return_data = true
  }

  tags = local.goa071_tags
}

resource "aws_cloudwatch_metric_alarm" "cv_processor_duration" {
  count = var.enable_lambda_workers ? 1 : 0

  alarm_name          = "${local.name_prefix}-cv-processor-duration"
  alarm_description   = "CV Processor Lambda duration is approaching its timeout."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = module.cv_processor_lambda[0].function_name }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 25000
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [module.observability.sns_topic_arn]
  ok_actions          = [module.observability.sns_topic_arn]

  tags = local.goa071_tags
}



