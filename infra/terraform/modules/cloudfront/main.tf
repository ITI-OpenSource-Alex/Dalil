locals {
  s3_origin_id  = "${var.name_prefix}-frontend-s3"
  alb_origin_id = "${var.name_prefix}-api-alb"
}

resource "aws_cloudfront_origin_access_control" "this" {
  count = var.enabled ? 1 : 0

  name                              = "${var.name_prefix}-frontend"
  description                       = "Private S3 access for the GOA frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_cache_policy" "static" {
  count = var.enabled ? 1 : 0

  name        = "${var.name_prefix}-static-86400"
  comment     = "Cache static frontend assets for one day"
  default_ttl = 86400
  max_ttl     = 31536000
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "none"
    }

    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

resource "aws_cloudfront_cache_policy" "api_disabled" {
  count = var.enabled ? 1 : 0

  name        = "${var.name_prefix}-api-no-cache"
  comment     = "Disable caching for API requests"
  default_ttl = 0
  max_ttl     = 0
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "none"
    }

    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

resource "aws_cloudfront_origin_request_policy" "api" {
  count = var.enabled ? 1 : 0

  name    = "${var.name_prefix}-api-all-viewer"
  comment = "Forward all viewer request data to the Gateway"

  cookies_config {
    cookie_behavior = "all"
  }

  headers_config {
    header_behavior = "allViewer"
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

resource "aws_cloudfront_distribution" "this" {
  count = var.enabled ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.name_prefix} public distribution"
  default_root_object = "index.html"
  price_class         = var.price_class
  aliases             = var.aliases
  web_acl_id          = var.web_acl_arn

  origin {
    domain_name              = var.s3_regional_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.this[0].id
  }

  origin {
    domain_name = var.alb_origin_domain_name
    origin_id   = local.alb_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = var.origin_protocol_policy
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.static[0].id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    target_origin_id         = local.alb_origin_id
    viewer_protocol_policy   = "https-only"
    compress                 = true
    cache_policy_id          = aws_cloudfront_cache_policy.api_disabled[0].id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.api[0].id
  }

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cloudfront" })

  lifecycle {
    precondition {
      condition = (
        var.s3_bucket_arn != null &&
        var.s3_regional_domain_name != null &&
        var.acm_certificate_arn != null &&
        var.web_acl_arn != null &&
        length(var.aliases) > 0
      )
      error_message = "Enabled CloudFront requires S3, ACM, WAF, and at least one alias."
    }
  }
}

data "aws_iam_policy_document" "frontend_bucket" {
  count = var.enabled ? 1 : 0

  statement {
    sid     = "AllowCloudFrontServicePrincipalReadOnly"
    actions = ["s3:GetObject"]
    resources = [
      "${var.s3_bucket_arn}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  count = var.enabled ? 1 : 0

  bucket = var.s3_bucket_name
  policy = data.aws_iam_policy_document.frontend_bucket[0].json
}
