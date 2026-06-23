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
  task_execution_secret_arns         = var.task_execution_secret_arns
  task_execution_kms_key_arns        = var.task_execution_kms_key_arns
  task_secret_arns                   = var.task_secret_arns
  task_sqs_queue_arns                = var.task_sqs_queue_arns
  task_kms_key_arns                  = var.task_kms_key_arns
  ecs_exec_operator_resource_arns    = var.ecs_exec_operator_resource_arns
  session_manager_log_retention_days = var.session_manager_log_retention_days
  session_manager_kms_key_id         = var.session_manager_kms_key_id
  tags                               = var.tags
}
