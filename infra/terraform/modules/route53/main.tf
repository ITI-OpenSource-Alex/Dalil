resource "aws_route53_zone" "this" {
  count = var.enabled && var.create_zone ? 1 : 0

  name = var.zone_name
  tags = merge(var.tags, { Name = var.zone_name })
}

locals {
  zone_id = var.enabled ? (
    var.create_zone ? aws_route53_zone.this[0].zone_id : var.existing_zone_id
  ) : null
}

resource "aws_route53_record" "root" {
  count = var.enabled && var.create_root_alias ? 1 : 0

  zone_id = local.zone_id
  name    = var.zone_name
  type    = "A"

  alias {
    name                   = var.root_alias_dns_name
    zone_id                = var.root_alias_zone_id
    evaluate_target_health = false
  }

  lifecycle {
    precondition {
      condition     = local.zone_id != null && var.root_alias_dns_name != null && var.root_alias_zone_id != null
      error_message = "The hosted zone and root alias target are required."
    }
  }
}

resource "aws_route53_record" "api" {
  count = var.enabled && var.create_api_alias ? 1 : 0

  zone_id = local.zone_id
  name    = "api.${var.zone_name}"
  type    = "A"

  alias {
    name                   = var.api_alias_dns_name
    zone_id                = var.api_alias_zone_id
    evaluate_target_health = true
  }

  lifecycle {
    precondition {
      condition     = local.zone_id != null && var.api_alias_dns_name != null && var.api_alias_zone_id != null
      error_message = "The hosted zone and API alias target are required."
    }
  }
}
