locals {
  name_prefix = "goa-${var.environment}"

  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = "security-groups"
      Project     = "goa"
    }
  )

  ecs_service_ports = {
    for port in var.ecs_service_ports : tostring(port) => port
  }

  alb_direct_service_ports = {
    for port in var.alb_direct_service_ports : tostring(port) => port
  }
}

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Allow public HTTP/HTTPS traffic to the application load balancer."
  vpc_id      = var.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-alb-sg"
      Tier = "public"
    }
  )
}

resource "aws_security_group" "gateway" {
  name        = "${local.name_prefix}-gateway-sg"
  description = "Allow traffic from the ALB to the gateway service only."
  vpc_id      = var.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-gateway-sg"
      Tier = "private"
      Role = "gateway"
    }
  )
}

resource "aws_security_group" "ecs_services" {
  name        = "${local.name_prefix}-ecs-services-sg"
  description = "Allow traffic from the gateway to internal ECS services only."
  vpc_id      = var.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-ecs-services-sg"
      Tier = "private"
      Role = "application"
    }
  )
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Allow database traffic from ECS services only."
  vpc_id      = var.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-rds-sg"
      Tier = "private"
      Role = "database"
    }
  )
}

resource "aws_security_group" "elasticache" {
  name        = "${local.name_prefix}-elasticache-sg"
  description = "Allow cache traffic from ECS services only."
  vpc_id      = var.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-elasticache-sg"
      Tier = "private"
      Role = "cache"
    }
  )
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  for_each = toset(var.alb_ingress_cidr_blocks)

  security_group_id = aws_security_group.alb.id
  description       = "Allow HTTP from the internet."
  cidr_ipv4         = each.value
  from_port         = 80
  ip_protocol       = "tcp"
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  for_each = toset(var.alb_ingress_cidr_blocks)

  security_group_id = aws_security_group.alb.id
  description       = "Allow HTTPS from the internet."
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "alb_to_gateway" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Allow ALB traffic to the gateway service."
  referenced_security_group_id = aws_security_group.gateway.id
  from_port                    = var.gateway_port
  ip_protocol                  = "tcp"
  to_port                      = var.gateway_port
}

resource "aws_vpc_security_group_ingress_rule" "gateway_from_alb" {
  security_group_id            = aws_security_group.gateway.id
  description                  = "Allow gateway traffic from the ALB only."
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = var.gateway_port
  ip_protocol                  = "tcp"
  to_port                      = var.gateway_port
}

resource "aws_vpc_security_group_egress_rule" "alb_to_ecs_services" {
  for_each = local.alb_direct_service_ports

  security_group_id            = aws_security_group.alb.id
  description                  = "Allow ALB routing and health checks to ECS services."
  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = each.value
  ip_protocol                  = "tcp"
  to_port                      = each.value
}

resource "aws_vpc_security_group_ingress_rule" "ecs_services_from_alb" {
  for_each = local.alb_direct_service_ports

  security_group_id            = aws_security_group.ecs_services.id
  description                  = "Allow ALB routing and health checks to ECS services."
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = each.value
  ip_protocol                  = "tcp"
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "gateway_to_ecs_services" {
  for_each = local.ecs_service_ports

  security_group_id            = aws_security_group.gateway.id
  description                  = "Allow gateway traffic to internal ECS services."
  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = each.value
  ip_protocol                  = "tcp"
  to_port                      = each.value
}

resource "aws_vpc_security_group_ingress_rule" "ecs_services_from_gateway" {
  for_each = local.ecs_service_ports

  security_group_id            = aws_security_group.ecs_services.id
  description                  = "Allow internal service traffic from the gateway only."
  referenced_security_group_id = aws_security_group.gateway.id
  from_port                    = each.value
  ip_protocol                  = "tcp"
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "ecs_services_to_rds" {
  security_group_id            = aws_security_group.ecs_services.id
  description                  = "Allow ECS services to reach RDS."
  referenced_security_group_id = aws_security_group.rds.id
  from_port                    = var.rds_port
  ip_protocol                  = "tcp"
  to_port                      = var.rds_port
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_ecs_services" {
  security_group_id            = aws_security_group.rds.id
  description                  = "Allow database traffic from ECS services only."
  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = var.rds_port
  ip_protocol                  = "tcp"
  to_port                      = var.rds_port
}

resource "aws_vpc_security_group_egress_rule" "ecs_services_to_elasticache" {
  security_group_id            = aws_security_group.ecs_services.id
  description                  = "Allow ECS services to reach ElastiCache."
  referenced_security_group_id = aws_security_group.elasticache.id
  from_port                    = var.elasticache_port
  ip_protocol                  = "tcp"
  to_port                      = var.elasticache_port
}

resource "aws_vpc_security_group_ingress_rule" "elasticache_from_ecs_services" {
  security_group_id            = aws_security_group.elasticache.id
  description                  = "Allow cache traffic from ECS services only."
  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = var.elasticache_port
  ip_protocol                  = "tcp"
  to_port                      = var.elasticache_port
}

resource "aws_vpc_security_group_egress_rule" "gateway_https" {
  for_each = toset(var.private_egress_cidr_blocks)

  security_group_id = aws_security_group.gateway.id
  description       = "Allow gateway HTTPS egress through NAT."
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "ecs_services_https" {
  for_each = toset(var.private_egress_cidr_blocks)

  security_group_id = aws_security_group.ecs_services.id
  description       = "Allow ECS service HTTPS egress through NAT."
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443
}

resource "aws_security_group" "lambda" {
  name        = "${local.name_prefix}-lambda-sg"
  description = "Outbound-only SG for GOA async worker Lambdas: RDS, ElastiCache, and internet via NAT."
  vpc_id      = var.vpc_id
  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-lambda-sg"
      Tier = "private"
      Role = "lambda"
    }
  )
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_rds" {
  security_group_id            = aws_security_group.lambda.id
  description                  = "Allow Lambda workers to reach RDS."
  referenced_security_group_id = aws_security_group.rds.id
  from_port                    = var.rds_port
  ip_protocol                  = "tcp"
  to_port                      = var.rds_port
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_lambda" {
  security_group_id            = aws_security_group.rds.id
  description                  = "Allow database traffic from Lambda workers."
  referenced_security_group_id = aws_security_group.lambda.id
  from_port                    = var.rds_port
  ip_protocol                  = "tcp"
  to_port                      = var.rds_port
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_elasticache" {
  security_group_id            = aws_security_group.lambda.id
  description                  = "Allow Lambda workers to reach ElastiCache."
  referenced_security_group_id = aws_security_group.elasticache.id
  from_port                    = var.elasticache_port
  ip_protocol                  = "tcp"
  to_port                      = var.elasticache_port
}

resource "aws_vpc_security_group_ingress_rule" "elasticache_from_lambda" {
  security_group_id            = aws_security_group.elasticache.id
  description                  = "Allow cache traffic from Lambda workers."
  referenced_security_group_id = aws_security_group.lambda.id
  from_port                    = var.elasticache_port
  ip_protocol                  = "tcp"
  to_port                      = var.elasticache_port
}

resource "aws_vpc_security_group_egress_rule" "lambda_https" {
  for_each          = toset(var.private_egress_cidr_blocks)
  security_group_id = aws_security_group.lambda.id
  description       = "Allow Lambda worker HTTPS egress through NAT (Secrets Manager, S3, third-party APIs)."
  cidr_ipv4         = each.value
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443
}
