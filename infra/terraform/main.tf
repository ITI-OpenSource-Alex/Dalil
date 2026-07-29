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
    for service, port in local.service_ports : port if service != "gateway"
  ]
  alb_direct_service_ports = [
    for service, port in local.service_ports : port if service != "gateway"
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

  environment                       = var.environment
  name_prefix                       = local.name_prefix
  cluster_id                        = module.ecs_cluster.cluster_id
  cluster_name                      = module.ecs_cluster.cluster_name
  service_connect_namespace_arn     = module.ecs_cluster.service_connect_namespace_arn
  service_name                      = each.key
  image_uri                         = each.value.image
  cpu                               = each.value.cpu
  memory                            = each.value.memory
  desired_count                     = each.value.desired_count
  container_port                    = each.value.container_port
  environment_variables             = each.value.environment
  secrets                           = each.value.secrets
  private_subnet_ids                = module.vpc.private_app_subnet_ids
  security_group_ids                = [each.key == "gateway" ? module.security_groups.gateway_security_group_id : module.security_groups.ecs_services_security_group_id]
  task_execution_role_arn           = module.iam.ecs_task_execution_role_arns[each.key]
  task_role_arn                     = module.iam.ecs_task_role_arns[each.key]
  target_group_arn                  = module.alb.target_group_arns[each.key]
  health_check_grace_period_seconds = each.value.health_check_grace_period_seconds
  log_group_name                    = module.observability.log_group_names[each.key]
  autoscaling_min_capacity          = 1
  autoscaling_max_capacity          = var.environment == "production" ? 10 : 4
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
    CV_EXTRACTION_MODEL    = "claude-haiku-4-5-20251001"
    WRITING_SECRET_ARN     = module.secrets.service_secret_arns["writing"]
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
  count         = var.enable_lambda_workers ? 1 : 0
  source        = "./modules/lambda"
  function_name = "goa-scholarship-matcher-${var.environment}"
  package_type  = "Image"
  image_uri     = "${module.ecr.repository_urls["scholarship-matcher"]}:${var.image_tag}"

  role_arn                       = module.iam.lambda_execution_role_arn
  vpc_subnet_ids                 = module.vpc.private_app_subnet_ids
  vpc_security_group_ids         = [module.security_groups.lambda_security_group_id]
  timeout                        = 300
  memory_size                    = 1024
  reserved_concurrent_executions = 5
  lambda_insights_layer_arn      = local.lambda_insights_layer_arn

  environment_variables = {
    ENVIRONMENT = var.environment
    WORKER      = "scholarship-matcher"
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
      ENVIRONMENT = var.environment
      WORKER      = "notification-sender"
    },
    { SQS_QUEUE_URL = module.sqs.queue_urls["notification"] }
  )

  tags = local.goa071_tags
}

# ---------------------------------------------------------------------------
# EventBridge cron rules
# ---------------------------------------------------------------------------

# NOTE: no "ingestion Lambda" exists in this ticket's scope — pointed at
# scholarship-matcher as a PLACEHOLDER so plan/apply succeeds. Swap for the
# real ingestion function once it exists, or drop this block if out of scope.
module "weekly_ingestion_rule" {
  count                = var.enable_lambda_workers ? 1 : 0
  source               = "./modules/eventbridge"
  rule_name            = "goa-weekly-ingestion-${var.environment}"
  description          = "Weekly ingestion run — Sunday 02:00 UTC"
  schedule_expression  = "cron(0 2 ? * SUN *)"
  target_function_name = module.scholarship_matcher_lambda[0].function_name # PLACEHOLDER
  target_function_arn  = module.scholarship_matcher_lambda[0].function_arn  # PLACEHOLDER
  tags                 = local.goa071_tags
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
  count = var.enable_lambda_workers && var.sqs_notification_queue_arn != null ? 1 : 0

  event_source_arn                   = module.sqs.queue_arns["notification"]
  function_name                      = module.notification_sender_lambda[0].function_name
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}
