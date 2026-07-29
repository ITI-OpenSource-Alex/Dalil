resource "tls_private_key" "this" {
  count = var.certificate_type == "self_signed" ? 1 : 0

  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "this" {
  count = var.certificate_type == "self_signed" ? 1 : 0

  private_key_pem = tls_private_key.this[0].private_key_pem

  subject {
    common_name  = var.domain_name
    organization = "GOA non-production"
  }

  validity_period_hours = 8760
  allowed_uses          = ["key_encipherment", "digital_signature", "server_auth"]
}

resource "aws_acm_certificate" "self_signed" {
  count = var.certificate_type == "self_signed" ? 1 : 0

  private_key      = tls_private_key.this[0].private_key_pem
  certificate_body = tls_self_signed_cert.this[0].cert_pem
  tags             = merge(var.tags, { Name = "${var.name_prefix}-alb-certificate" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate" "public" {
  count = var.certificate_type == "public_dns" ? 1 : 0

  domain_name               = var.domain_name
  subject_alternative_names = var.subject_alternative_names
  validation_method         = "DNS"
  tags                      = merge(var.tags, { Name = "${var.name_prefix}-public-certificate" })

  lifecycle {
    create_before_destroy = true

    precondition {
      condition     = var.route53_zone_id != null
      error_message = "route53_zone_id is required for a public DNS-validated certificate."
    }
  }
}

resource "aws_route53_record" "validation" {
  for_each = var.certificate_type == "public_dns" ? {
    for option in aws_acm_certificate.public[0].domain_validation_options :
    option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  } : {}

  allow_overwrite = true
  zone_id         = var.route53_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
}

resource "aws_acm_certificate_validation" "public" {
  count = var.certificate_type == "public_dns" ? 1 : 0

  certificate_arn         = aws_acm_certificate.public[0].arn
  validation_record_fqdns = [for record in aws_route53_record.validation : record.fqdn]
}
