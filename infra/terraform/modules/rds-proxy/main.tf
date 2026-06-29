locals {
  proxy_name = "${var.name_prefix}-postgres-proxy"
}

resource "aws_db_proxy" "this" {
  name                   = local.proxy_name
  debug_logging          = false
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = var.idle_client_timeout_seconds
  require_tls            = var.require_tls
  role_arn               = var.iam_role_arn
  vpc_security_group_ids = var.vpc_security_group_ids
  vpc_subnet_ids         = var.vpc_subnet_ids

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = var.db_secret_arn
  }

  tags = merge(var.tags, {
    Name = local.proxy_name
  })
}

resource "aws_db_proxy_default_target_group" "this" {
  db_proxy_name = aws_db_proxy.this.name

  connection_pool_config {
    connection_borrow_timeout    = var.connection_borrow_timeout_seconds
    max_connections_percent      = var.max_connections_percent
    max_idle_connections_percent = var.max_idle_connections_percent
    session_pinning_filters      = var.session_pinning_filters
  }
}

resource "aws_db_proxy_target" "this" {
  db_instance_identifier = var.db_instance_identifier
  db_proxy_name          = aws_db_proxy.this.name
  target_group_name      = aws_db_proxy_default_target_group.this.name
}
