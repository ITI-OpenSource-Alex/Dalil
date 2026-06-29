locals {
  cluster_id = "${var.name_prefix}-redis"
}

resource "aws_security_group" "this" {
  name        = "${local.cluster_id}-sg"
  description = "Redis access for GOA services."
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${local.cluster_id}-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_service" {
  for_each = {
    for index, security_group_id in var.allowed_security_group_ids :
    index => security_group_id
  }

  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = var.port
  to_port                      = var.port
  description                  = "Allow Redis from approved GOA workload security group."

  tags = merge(var.tags, {
    Name = "${local.cluster_id}-redis-from-service"
  })
}

resource "aws_elasticache_subnet_group" "this" {
  name        = "${local.cluster_id}-subnets"
  description = "Private subnets for GOA Redis."
  subnet_ids  = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${local.cluster_id}-subnets"
  })
}

resource "aws_elasticache_parameter_group" "this" {
  name        = "${local.cluster_id}-params"
  family      = var.parameter_group_family
  description = "GOA Redis parameters."

  parameter {
    name  = "databases"
    value = tostring(var.database_count)
  }

  tags = merge(var.tags, {
    Name = "${local.cluster_id}-params"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = local.cluster_id
  description          = "GOA Redis for Gateway rate limits and Orchestration session memory."

  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  num_cache_clusters   = var.num_cache_clusters
  port                 = var.port
  parameter_group_name = aws_elasticache_parameter_group.this.name
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [aws_security_group.this.id]

  automatic_failover_enabled = var.num_cache_clusters > 1
  multi_az_enabled           = var.num_cache_clusters > 1

  at_rest_encryption_enabled = var.at_rest_encryption_enabled
  transit_encryption_enabled = var.transit_encryption_enabled
  auth_token                 = var.auth_token

  snapshot_retention_limit = var.snapshot_retention_limit
  maintenance_window       = var.maintenance_window
  apply_immediately        = var.apply_immediately

  tags = merge(var.tags, {
    Name = local.cluster_id
  })

  lifecycle {
    precondition {
      condition     = var.auth_token == null || var.transit_encryption_enabled
      error_message = "Redis auth_token requires transit_encryption_enabled to be true."
    }

    precondition {
      condition     = var.database_count > 1
      error_message = "GOA-070 requires at least two Redis logical databases."
    }
  }
}
