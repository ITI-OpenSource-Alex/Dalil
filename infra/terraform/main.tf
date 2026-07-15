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

  environment = var.environment
  vpc_id      = module.vpc.vpc_id
  tags        = var.tags
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

module "alb" {
  source = "./modules/alb"

  environment                = var.environment
  vpc_id                     = module.vpc.vpc_id
  public_subnet_ids          = module.vpc.public_subnet_ids
  alb_security_group_id      = module.security_groups.alb_security_group_id
  certificate_arn            = var.alb_certificate_arn
  enable_deletion_protection = var.alb_enable_deletion_protection
  default_target_group_name  = var.alb_default_target_group_name
  target_groups              = var.alb_target_groups
  tags                       = var.tags
}

module "iam" {
  source = "./modules/iam"

  environment                        = var.environment
  task_execution_secret_arns         = distinct(concat(var.task_execution_secret_arns, values(module.secrets.service_secret_arns)))
  task_execution_kms_key_arns        = var.task_execution_kms_key_arns
  task_secret_arns                   = distinct(concat(var.task_secret_arns, values(module.secrets.service_secret_arns)))
  task_sqs_queue_arns                = distinct(concat(var.task_sqs_queue_arns, values(module.sqs.queue_arns)))
  task_kms_key_arns                  = var.task_kms_key_arns
  ecs_exec_operator_resource_arns    = var.ecs_exec_operator_resource_arns
  session_manager_log_retention_days = var.session_manager_log_retention_days
  session_manager_kms_key_id         = var.session_manager_kms_key_id
  lambda_secret_arns                 = distinct(concat(var.lambda_secret_arns, values(module.secrets.service_secret_arns)))
  lambda_sqs_queue_arns              = distinct(concat(var.sqs_notification_queue_arn != null ? [var.sqs_notification_queue_arn] : [], values(module.sqs.queue_arns)))
  tags                               = var.tags
}

data "aws_region" "current" {}

data "aws_partition" "current" {}

locals {
  goa071_tags = merge(var.tags, {
    Ticket = "GOA-071"
  })

  cv_upload_prefix           = "cvs/"
  lambda_insights_layer_arn  = "arn:${data.aws_partition.current.partition}:lambda:${data.aws_region.current.name}:580247275435:layer:LambdaInsightsExtension:14"
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
  source        = "./modules/lambda"
  function_name = "goa-cv-processor-${var.environment}"
  package_type  = "Image"
  image_uri     = "${var.ecr_cv_processor_repo_url}:${var.image_tag}"

  role_arn                       = module.iam.lambda_execution_role_arn
  vpc_subnet_ids                 = module.vpc.private_app_subnet_ids
  vpc_security_group_ids         = [module.security_groups.lambda_security_group_id]
  timeout                        = 120
  memory_size                    = 1024
  reserved_concurrent_executions = 20
  lambda_insights_layer_arn      = local.lambda_insights_layer_arn

  environment_variables = {
    ENVIRONMENT = var.environment
    WORKER      = "cv-processor"
  }

  tags = local.goa071_tags
}

module "scholarship_matcher_lambda" {
  source        = "./modules/lambda"
  function_name = "goa-scholarship-matcher-${var.environment}"
  package_type  = "Image"
  image_uri     = "${var.ecr_scholarship_matcher_repo_url}:${var.image_tag}"

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
  source        = "./modules/lambda"
  function_name = "goa-notification-sender-${var.environment}"
  package_type  = "Image"
  image_uri     = "${var.ecr_notification_sender_repo_url}:${var.image_tag}"

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
  source               = "./modules/eventbridge"
  rule_name            = "goa-weekly-ingestion-${var.environment}"
  description          = "Weekly ingestion run — Sunday 02:00 UTC"
  schedule_expression  = "cron(0 2 ? * SUN *)"
  target_function_name = module.scholarship_matcher_lambda.function_name # PLACEHOLDER
  target_function_arn  = module.scholarship_matcher_lambda.function_arn  # PLACEHOLDER
  tags                 = local.goa071_tags
}

module "daily_scholarship_match_rule" {
  source               = "./modules/eventbridge"
  rule_name            = "goa-daily-scholarship-match-${var.environment}"
  description          = "Daily scholarship matching run — 08:00 UTC"
  schedule_expression  = "cron(0 8 * * ? *)"
  target_function_name = module.scholarship_matcher_lambda.function_name
  target_function_arn  = module.scholarship_matcher_lambda.function_arn
  tags                 = local.goa071_tags
}

# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------

resource "aws_lambda_permission" "s3_invoke_cv_processor" {
  statement_id   = "AllowExecutionFromS3WritingFiles"
  action         = "lambda:InvokeFunction"
  function_name  = module.cv_processor_lambda.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = module.writing_files_bucket.bucket_arn
  source_account = var.aws_account_id
}

resource "aws_s3_bucket_notification" "writing_files" {
  bucket = module.writing_files_bucket.bucket_id

  lambda_function {
    lambda_function_arn = module.cv_processor_lambda.function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.cv_upload_prefix
  }

  depends_on = [aws_lambda_permission.s3_invoke_cv_processor]
}

# Skipped entirely until modules/sqs exists and sqs_notification_queue_arn
# is set — this whole resource is conditionally created via count.
resource "aws_lambda_event_source_mapping" "sqs_to_notification_sender" {
  count = var.sqs_notification_queue_arn != null ? 1 : 0

  event_source_arn                   = module.sqs.queue_arns["notification"]
  function_name                      = module.notification_sender_lambda.function_name
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}
