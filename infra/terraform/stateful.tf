module "sqs" {
  source = "./modules/sqs"

  name_prefix = local.name_prefix
  queues      = local.sqs_queues
  tags        = local.common_tags
}

module "secrets" {
  source = "./modules/secrets"

  name_prefix           = local.name_prefix
  service_secret_keys   = local.service_secret_keys
  database_names        = local.postgres_databases
  rds_proxy_endpoint    = var.enable_rds_proxy ? module.rds_proxy[0].proxy_endpoint : module.rds.instance_address
  service_secret_values = var.service_secret_values
  kms_key_id            = var.secrets_kms_key_id
  tags                  = local.common_tags
}

resource "aws_security_group" "rds_proxy" {
  name        = "${local.name_prefix}-rds-proxy-sg"
  description = "RDS Proxy access for GOA workloads."
  vpc_id      = module.vpc.vpc_id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-rds-proxy-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "rds_proxy_from_workload" {
  for_each = var.enable_rds_proxy ? {
    ecs    = module.security_groups.ecs_services_security_group_id
    lambda = module.security_groups.lambda_security_group_id
  } : {}

  security_group_id            = aws_security_group.rds_proxy.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Allow PostgreSQL proxy access from GOA workloads."
}

resource "aws_vpc_security_group_egress_rule" "rds_proxy_to_rds" {
  count                        = var.enable_rds_proxy ? 1 : 0
  security_group_id            = aws_security_group.rds_proxy.id
  referenced_security_group_id = module.rds.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Allow RDS Proxy to connect to PostgreSQL."
}

data "aws_iam_policy_document" "rds_proxy_assume_role" {
  count = var.enable_rds_proxy ? 1 : 0
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rds_proxy" {
  count              = var.enable_rds_proxy ? 1 : 0
  name               = "${local.name_prefix}-rds-proxy"
  assume_role_policy = data.aws_iam_policy_document.rds_proxy_assume_role[0].json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "rds_proxy_secret" {
  count = var.enable_rds_proxy ? 1 : 0
  statement {
    actions   = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
    resources = [module.secrets.rds_master_secret_arn]
  }
}

resource "aws_iam_role_policy" "rds_proxy_secret" {
  count  = var.enable_rds_proxy ? 1 : 0
  name   = "${local.name_prefix}-rds-proxy-secret"
  role   = aws_iam_role.rds_proxy[0].id
  policy = data.aws_iam_policy_document.rds_proxy_secret[0].json
}

module "rds" {
  source = "./modules/rds"

  name_prefix        = local.name_prefix
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_data_subnet_ids
  allowed_security_group_ids = var.enable_rds_proxy ? [aws_security_group.rds_proxy.id] : [
    module.security_groups.ecs_services_security_group_id,
    module.security_groups.lambda_security_group_id,
  ]
  database_names               = local.postgres_databases
  instance_class               = local.rds_instance_class
  multi_az                     = local.rds_multi_az
  allocated_storage_gb         = var.rds_allocated_storage_gb
  max_allocated_storage_gb     = var.rds_max_allocated_storage_gb
  engine_version               = var.rds_engine_version
  backup_retention_days        = var.rds_backup_retention_days
  performance_insights_enabled = var.rds_performance_insights_enabled
  master_username              = module.secrets.rds_master_username
  master_password              = module.secrets.rds_master_password
  master_secret_arn            = module.secrets.rds_master_secret_arn
  deletion_protection          = var.environment == "production"
  skip_final_snapshot          = var.environment != "production"
  tags                         = local.common_tags
}

module "rds_proxy" {
  count  = var.enable_rds_proxy ? 1 : 0
  source = "./modules/rds-proxy"

  name_prefix            = local.name_prefix
  vpc_subnet_ids         = module.vpc.private_data_subnet_ids
  vpc_security_group_ids = [aws_security_group.rds_proxy.id]
  db_instance_identifier = module.rds.instance_identifier
  db_secret_arn          = module.secrets.rds_master_secret_arn
  iam_role_arn           = aws_iam_role.rds_proxy[0].arn
  database_names         = local.postgres_databases
  tags                   = local.common_tags

  depends_on = [aws_iam_role_policy.rds_proxy_secret]
}

moved {
  from = aws_security_group.rds_proxy[0]
  to   = aws_security_group.rds_proxy
}

module "elasticache" {
  source = "./modules/elasticache"

  name_prefix        = local.name_prefix
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_data_subnet_ids
  allowed_security_group_ids = [
    module.security_groups.gateway_security_group_id,
    module.security_groups.ecs_services_security_group_id,
    module.security_groups.lambda_security_group_id,
  ]
  node_type                  = local.redis_node_type
  logical_databases          = local.redis_logical_databases
  num_cache_clusters         = var.redis_num_cache_clusters
  transit_encryption_enabled = var.redis_transit_encryption_enabled
  auth_token                 = var.redis_auth_token
  tags                       = local.common_tags
}

module "observability" {
  source = "./modules/observability"

  name_prefix           = local.name_prefix
  service_names         = local.service_names
  log_retention_days    = 30
  sns_topic_name        = "goa-alerts"
  alert_email_addresses = var.alert_email_addresses
  sqs_queue_names       = values(module.sqs.dlq_names)
  ecs_cluster_name      = var.ecs_cluster_name
  alarm_definitions     = local.goa027_alarm_definitions
  tags                  = local.common_tags
}
