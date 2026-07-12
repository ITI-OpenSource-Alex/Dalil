resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(var.service_names)

  name              = "/aws/ecs/${var.name_prefix}/${each.key}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${each.key}-logs"
    Service = each.key
  })
}

resource "aws_sns_topic" "alerts" {
  name = var.sns_topic_name

  tags = merge(var.tags, {
    Name = var.sns_topic_name
  })
}

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.alert_email_addresses)

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each = var.alarm_definitions

  alarm_name        = coalesce(each.value.alarm_name, "${var.name_prefix}-${each.key}")
  alarm_description = coalesce(each.value.description, "GOA-027 alarm: ${each.key}")

  namespace   = each.value.namespace
  metric_name = each.value.metric_name
  dimensions  = each.value.dimensions

  comparison_operator = each.value.comparison_operator
  threshold           = each.value.threshold
  evaluation_periods  = each.value.evaluation_periods
  datapoints_to_alarm = each.value.datapoints_to_alarm
  period              = each.value.period
  statistic           = each.value.statistic
  extended_statistic  = each.value.extended_statistic
  unit                = each.value.unit
  treat_missing_data  = each.value.treat_missing_data

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = merge(var.tags, {
    Name = coalesce(each.value.alarm_name, "${var.name_prefix}-${each.key}")
  })
}
