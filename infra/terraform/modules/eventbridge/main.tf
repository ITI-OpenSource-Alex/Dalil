resource "aws_cloudwatch_event_rule" "this" {
  name                = var.rule_name
  description         = var.description
  schedule_expression = var.schedule_expression
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "this" {
  rule      = aws_cloudwatch_event_rule.this.name
  target_id = var.rule_name
  arn       = var.target_function_arn
  role_arn  = var.target_role_arn
  input     = var.input

  retry_policy {
    maximum_retry_attempts       = var.maximum_retry_attempts
    maximum_event_age_in_seconds = var.maximum_event_age_in_seconds
  }

  dynamic "dead_letter_config" {
    for_each = var.dlq_arn == null ? [] : [var.dlq_arn]
    content {
      arn = dead_letter_config.value
    }
  }

  dynamic "ecs_target" {
    for_each = var.target_type == "ecs" ? [1] : []
    content {
      task_definition_arn = var.ecs_task_definition_arn
      task_count          = 1
      launch_type         = "FARGATE"

      network_configuration {
        assign_public_ip = false
        subnets          = var.ecs_subnet_ids
        security_groups  = var.ecs_security_group_ids
      }
    }
  }
}

resource "aws_lambda_permission" "allow_eventbridge" {
  count         = var.target_type == "lambda" ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge-${var.rule_name}"
  action        = "lambda:InvokeFunction"
  function_name = var.target_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.this.arn
}
