locals {
  identifier          = "${var.name_prefix}-postgres"
  database_names      = sort(values(var.database_names))
  database_values_sql = join(",\n", [for database_name in local.database_names : format("  ('%s')", database_name)])

  database_bootstrap_sql = <<-SQL
    \set ON_ERROR_STOP on

    SELECT format('CREATE DATABASE %I', database_name)
    FROM (VALUES
    ${local.database_values_sql}
    ) AS requested_databases(database_name)
    WHERE NOT EXISTS (
      SELECT 1
      FROM pg_database
      WHERE datname = requested_databases.database_name
    )
    \gexec
  SQL
}

# Retained during the GOA-070 migration so Terraform never attempts to detach
# an RDS-managed ENI. It has no ingress rules and is no longer used after the
# DB instance switches to the shared security-groups module.
resource "aws_security_group" "this" {
  name        = "${local.identifier}-sg"
  description = "PostgreSQL access for GOA services."
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${local.identifier}-sg"
  })
}

resource "aws_db_subnet_group" "this" {
  name        = "${local.identifier}-subnets"
  description = "Private data subnets for GOA PostgreSQL."
  subnet_ids  = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${local.identifier}-subnets"
  })
}

resource "aws_db_parameter_group" "this" {
  name        = "${local.identifier}-params"
  description = "GOA PostgreSQL parameters."
  family      = var.parameter_group_family

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = merge(var.tags, {
    Name = "${local.identifier}-params"
  })
}

resource "aws_db_instance" "this" {
  identifier = local.identifier

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_encrypted     = var.storage_encrypted
  kms_key_id            = var.storage_kms_key_id
  storage_type          = "gp3"

  username = var.master_username
  password = var.master_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  parameter_group_name   = aws_db_parameter_group.this.name
  publicly_accessible    = false
  multi_az               = var.multi_az

  backup_retention_period = var.backup_retention_days
  backup_window           = var.backup_window
  maintenance_window      = var.maintenance_window
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade   = true
  performance_insights_enabled = var.performance_insights_enabled

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : coalesce(var.final_snapshot_identifier, "${local.identifier}-final")

  tags = merge(var.tags, {
    Name = local.identifier
  })

  lifecycle {
    precondition {
      condition     = var.environment == "production" ? var.multi_az : !var.multi_az
      error_message = "GOA-070 requires Multi-AZ to be enabled in production only."
    }

    precondition {
      condition     = var.environment == "production" ? var.deletion_protection : true
      error_message = "Production RDS must have deletion protection enabled."
    }
  }
}
