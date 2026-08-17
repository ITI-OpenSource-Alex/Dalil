locals {
  name_prefix = "goa-${var.environment}"

  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = "alb"
      Project     = "goa"
    }
  )
}

resource "aws_lb" "this" {
  name                       = "${local.name_prefix}-alb"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [var.alb_security_group_id]
  subnets                    = var.public_subnet_ids
  enable_deletion_protection = var.enable_deletion_protection
  enable_http2               = true
  drop_invalid_header_fields = true

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-alb"
      Tier = "public"
    }
  )
}

resource "aws_lb_target_group" "this" {
  for_each = var.target_groups

  name                 = substr("${local.name_prefix}-${each.key}-tg", 0, 32)
  port                 = each.value.port
  protocol             = each.value.protocol
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = each.value.deregistration_delay

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200-399"
    path                = each.value.health_check_path
    port                = "traffic-port"
    protocol            = each.value.protocol
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = merge(
    local.common_tags,
    {
      Name    = substr("${local.name_prefix}-${each.key}-tg", 0, 32)
      Service = each.key
    }
  )
}

resource "aws_lb_listener" "http_redirect" {
  count = var.enable_https_listener ? 1 : 0

  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "http_forward" {
  count = var.enable_https_listener ? 0 : 1

  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[var.default_target_group_name].arn
  }
}

resource "aws_lb_listener" "https" {
  count = var.enable_https_listener ? 1 : 0

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  ssl_policy        = var.ssl_policy

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[var.default_target_group_name].arn
  }
}

resource "aws_lb_listener_rule" "path_routes" {
  for_each = var.listener_rules

  listener_arn = var.enable_https_listener ? aws_lb_listener.https[0].arn : aws_lb_listener.http_forward[0].arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[each.value.target_group_name].arn
  }

  condition {
    path_pattern {
      values = each.value.path_patterns
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${each.key}"
  })
}
