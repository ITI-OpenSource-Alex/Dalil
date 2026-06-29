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
  rds_proxy_endpoint    = module.rds_proxy.proxy_endpoint
  service_secret_values = var.service_secret_values
  kms_key_id            = var.secrets_kms_key_id
  tags                  = local.common_tags
}

resource "aws_security_group" "rds_proxy" {
  name        = "${local.name_prefix}-rds-proxy-sg"
  description = "RDS Proxy access for GOA workloads."
  vpc_id      = var.goa069_vpc_id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-proxy-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "rds_proxy_from_workload" {
  for_each = toset(var.goa069_workload_security_group_ids)

  security_group_id            = aws_security_group.rds_proxy.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Allow PostgreSQL proxy access from GOA workloads."

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-proxy-from-workload"
  })
}

resource "aws_vpc_security_group_egress_rule" "rds_proxy_to_rds" {
  security_group_id            = aws_security_group.rds_proxy.id
  referenced_security_group_id = module.rds.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Allow RDS Proxy to connect to PostgreSQL."

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-proxy-to-rds"
  })
}

data "aws_iam_policy_document" "rds_proxy_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rds_proxy" {
  name               = "${local.name_prefix}-rds-proxy"
  assume_role_policy = data.aws_iam_policy_document.rds_proxy_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-proxy"
  })
}

data "aws_iam_policy_document" "rds_proxy_secret" {
  statement {
    sid = "ReadRdsMasterSecret"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]
    resources = [module.secrets.rds_master_secret_arn]
  }
}

resource "aws_iam_role_policy" "rds_proxy_secret" {
  name   = "${local.name_prefix}-rds-proxy-secret"
  role   = aws_iam_role.rds_proxy.id
  policy = data.aws_iam_policy_document.rds_proxy_secret.json
}

module "rds" {
  source = "./modules/rds"

  name_prefix                = local.name_prefix
  environment                = var.environment
  vpc_id                     = var.goa069_vpc_id
  private_subnet_ids         = var.goa069_private_data_subnet_ids
  allowed_security_group_ids = [aws_security_group.rds_proxy.id]
  database_names             = local.postgres_databases
  instance_class             = local.rds_instance_class
  multi_az                   = local.rds_multi_az
  allocated_storage_gb       = var.rds_allocated_storage_gb
  max_allocated_storage_gb   = var.rds_max_allocated_storage_gb
  engine_version             = var.rds_engine_version
  master_username            = module.secrets.rds_master_username
  master_password            = module.secrets.rds_master_password
  master_secret_arn          = module.secrets.rds_master_secret_arn
  deletion_protection        = var.environment == "production"
  skip_final_snapshot        = var.environment != "production"
  tags                       = local.common_tags
}

module "rds_proxy" {
  source = "./modules/rds-proxy"

  name_prefix            = local.name_prefix
  vpc_subnet_ids         = var.goa069_private_data_subnet_ids
  vpc_security_group_ids = [aws_security_group.rds_proxy.id]
  db_instance_identifier = module.rds.instance_identifier
  db_secret_arn          = module.secrets.rds_master_secret_arn
  iam_role_arn           = aws_iam_role.rds_proxy.arn
  database_names         = local.postgres_databases
  tags                   = local.common_tags

  depends_on = [
    aws_iam_role_policy.rds_proxy_secret,
  ]
}

module "elasticache" {
  source = "./modules/elasticache"

  name_prefix                = local.name_prefix
  vpc_id                     = var.goa069_vpc_id
  private_subnet_ids         = var.goa069_private_data_subnet_ids
  allowed_security_group_ids = var.goa069_workload_security_group_ids
  node_type                  = local.redis_node_type
  logical_databases          = local.redis_logical_databases
  num_cache_clusters         = var.redis_num_cache_clusters
  transit_encryption_enabled = var.redis_transit_encryption_enabled
  auth_token                 = var.redis_auth_token
  tags                       = local.common_tags
}

module "iam" {
  source = "./modules/iam"

  name_prefix            = local.name_prefix
  service_names          = local.service_names
  service_secret_arns    = local.service_secret_arns
  service_sqs_queue_arns = local.service_sqs_queue_arns
  execution_secret_arns  = local.service_secret_arns
  github_repository      = var.github_repository
  ecs_cluster_arn        = var.goa069_ecs_cluster_arn
  ecs_service_arns       = values(var.goa069_ecs_service_arns)
  ecr_repository_arns    = values(var.goa069_ecr_repository_arns)
  task_definition_arns   = values(var.goa069_task_definition_arns)
  tags                   = local.common_tags
}

module "observability" {
  source = "./modules/observability"

  name_prefix           = local.name_prefix
  service_names         = local.service_names
  log_retention_days    = 30
  sns_topic_name        = "goa-alerts"
  alert_email_addresses = var.alert_email_addresses
  sqs_queue_names       = values(module.sqs.dlq_names)
  ecs_cluster_name      = var.goa069_ecs_cluster_name
  alarm_definitions     = local.goa027_alarm_definitions
  tags                  = local.common_tags
}
