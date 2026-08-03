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

resource "aws_cloudwatch_dashboard" "goa_overview" {
  dashboard_name = var.dashboard_name

  dashboard_body = jsonencode({
    start          = "-PT6H"
    periodOverride = "inherit"
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Requests/s per service"
          view   = "timeSeries"
          region = var.aws_region
          period = 60
          stat   = "Average"
          metrics = [
            for service in var.service_names :
            ["GOA/Services", "RequestsPerSecond", "Service", service]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "P95 latency per service"
          view   = "timeSeries"
          region = var.aws_region
          period = 60
          stat   = "p95"
          metrics = [
            for service in var.service_names :
            ["GOA/Services", "LatencyMs", "Service", service]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Error rate (%)"
          view   = "timeSeries"
          region = var.aws_region
          period = 60
          stat   = "Average"
          metrics = [
            for service in var.service_names :
            ["GOA/Services", "ErrorRate", "Service", service]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Active WebSocket connections"
          view   = "timeSeries"
          region = var.aws_region
          period = 60
          stat   = "Maximum"
          metrics = [
            ["GOA/Services", "ActiveWebSocketConnections", "Service", "speaking"]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Lambda invocation count"
          view   = "timeSeries"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            for function_name in var.lambda_function_names :
            ["AWS/Lambda", "Invocations", "FunctionName", function_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "DLQ message count"
          view   = "timeSeries"
          region = var.aws_region
          period = 60
          stat   = "Maximum"
          metrics = [
            for queue_name in var.sqs_queue_names :
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", queue_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 24
        height = 6
        properties = {
          title  = "ECS running task count"
          view   = "timeSeries"
          region = var.aws_region
          period = 60
          metrics = [
            [{
              expression = "SEARCH('{ECS/ContainerInsights,ClusterName,ServiceName} MetricName=\"RunningTaskCount\" AND ClusterName=\"${var.ecs_cluster_name}\"', 'Minimum', 60)"
              id         = "runningTasks"
              label      = "Running tasks"
            }]
          ]
        }
      }
    ]
  })
}
