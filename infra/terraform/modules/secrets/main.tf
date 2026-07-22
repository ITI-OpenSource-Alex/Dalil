locals {
  services_requiring_jwt_secret = toset([
    for service, keys in var.service_secret_keys : service
    if contains(keys, "JWT_SECRET")
  ])

  services_requiring_internal_api_key = toset([
    for service, keys in var.service_secret_keys : service
    if contains(keys, "INTERNAL_API_KEY")
  ])

  database_url_by_service = {
    for service, database_name in var.database_names :
    service => var.rds_proxy_endpoint == null || var.rds_proxy_endpoint == "" ? "" : format(
      "postgresql://%s:%s@%s:%s/%s",
      urlencode(var.rds_master_username),
      urlencode(random_password.rds_master.result),
      var.rds_proxy_endpoint,
      var.postgres_port,
      database_name
    )
  }

  generated_service_secret_values = {
    for service, keys in var.service_secret_keys :
    service => {
      for key in keys :
      key => (
        key == "JWT_SECRET" ? random_password.jwt_secret[service].result :
        key == "INTERNAL_API_KEY" ? random_password.internal_api_key[service].result :
        key == "DATABASE_URL" ? lookup(local.database_url_by_service, service, "") :
        ""
      )
    }
  }

  service_secret_payloads = {
    for service, generated_values in local.generated_service_secret_values :
    service => merge(generated_values, lookup(var.service_secret_values, service, {}))
  }
}

resource "random_password" "rds_master" {
  length           = var.rds_master_password_length
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "jwt_secret" {
  for_each = local.services_requiring_jwt_secret

  length           = 48
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "internal_api_key" {
  for_each = local.services_requiring_internal_api_key

  length  = 40
  special = false
}

resource "aws_secretsmanager_secret" "rds_master" {
  name                    = "${var.name_prefix}/rds/master"
  description             = "GOA PostgreSQL master credentials."
  kms_key_id              = var.kms_key_id
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-rds-master"
  })
}

resource "aws_secretsmanager_secret_version" "rds_master" {
  secret_id = aws_secretsmanager_secret.rds_master.id

  secret_string = jsonencode({
    engine   = "postgres"
    username = var.rds_master_username
    password = random_password.rds_master.result
    port     = var.postgres_port
  })
}

resource "aws_secretsmanager_secret" "service" {
  for_each = var.service_secret_keys

  name                    = "${var.name_prefix}/${each.key}"
  description             = "GOA ${each.key} service secrets."
  kms_key_id              = var.kms_key_id
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${each.key}-secrets"
    Service = each.key
  })
}

resource "aws_secretsmanager_secret_version" "service" {
  for_each = var.service_secret_keys

  secret_id     = aws_secretsmanager_secret.service[each.key].id
  secret_string = jsonencode(local.service_secret_payloads[each.key])
}
