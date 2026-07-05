locals {
  name_prefix = "goa-${var.environment}"

  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = "vpc-endpoints"
      Project     = "goa"
    }
  )
}

resource "aws_security_group" "interface_endpoints" {
  name        = "${local.name_prefix}-interface-endpoints-sg"
  description = "Allow private application traffic to interface VPC endpoints."
  vpc_id      = var.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-interface-endpoints-sg"
      Tier = "private"
      Role = "vpc-endpoints"
    }
  )
}

resource "aws_vpc_security_group_ingress_rule" "interface_endpoints_https" {
  for_each = toset(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.interface_endpoints.id
  description                  = "Allow HTTPS from private application security groups."
  referenced_security_group_id = each.value
  from_port                    = 443
  ip_protocol                  = "tcp"
  to_port                      = 443
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.s3_route_table_ids

  tags = merge(
    local.common_tags,
    {
      Name    = "${local.name_prefix}-s3-endpoint"
      Service = "s3"
      Type    = "gateway"
    }
  )
}

resource "aws_vpc_endpoint" "secrets_manager" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.interface_endpoint_subnet_ids
  security_group_ids  = [aws_security_group.interface_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    local.common_tags,
    {
      Name    = "${local.name_prefix}-secrets-manager-endpoint"
      Service = "secretsmanager"
      Type    = "interface"
    }
  )
}

resource "aws_vpc_endpoint" "sqs" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.sqs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.interface_endpoint_subnet_ids
  security_group_ids  = [aws_security_group.interface_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    local.common_tags,
    {
      Name    = "${local.name_prefix}-sqs-endpoint"
      Service = "sqs"
      Type    = "interface"
    }
  )
}
