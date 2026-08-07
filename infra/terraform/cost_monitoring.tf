# GOA-046 — cost monitoring.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE IS GATED OFF BY DEFAULT
#
# Everything here is written, reviewed and ready, and none of it has been
# applied. The IAM user this project runs as carries an explicit deny:
#
#   arn:aws:iam::114403655381:policy/DenyBillingAccess
#
#   $ aws budgets describe-budgets --account-id 114403655381
#   AccessDeniedException: not authorized to perform budgets:ViewBudget ...
#     with an explicit deny in an identity-based policy
#
#   $ aws ce get-cost-and-usage ...
#   AccessDeniedException: not authorized to perform ce:GetCostAndUsage ...
#     with an explicit deny in an identity-based policy
#
# The account is administered by the institute rather than by this team, so the
# deny is not ours to lift and this is a permanent constraint, not a pending
# credential. An explicit deny also beats any Allow we could attach, so no role
# or policy written here can work around it while the policy is in force.
#
# The resource-tagging half of GOA-046 does NOT depend on billing permissions
# and IS applied — see the default_tags block in providers.tf and the Service
# tag in locals.tf. Tag coverage is verifiable today through
# resourcegroupstaggingapi, which the deny does not cover.
#
# To enable, once an account with billing access is available:
#   enable_cost_monitoring = true   (and set cost_report_* in the tfvars)
# ─────────────────────────────────────────────────────────────────────────────

locals {
  cost_monitoring_enabled = var.enable_cost_monitoring ? 1 : 0
}

# AWS Budgets: $150/month with alerts at 80% and 100%.
#
# ACTUAL thresholds, not FORECASTED. A forecast alert on a workload this spiky —
# an ingestion crawl or a load test moves the daily rate by an order of
# magnitude — fires constantly on projections that never materialise, and an
# alert people learn to ignore is worse than none.
resource "aws_budgets_budget" "monthly" {
  count = local.cost_monitoring_enabled

  name         = "${var.project_name}-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$${var.project_name}"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.cost_report_recipients
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.cost_report_recipients
  }
}

data "archive_file" "cost_report" {
  count = local.cost_monitoring_enabled

  type        = "zip"
  source_dir  = "${path.module}/lambda/cost_report"
  output_path = "${path.module}/.terraform/tmp/cost-report.zip"
}

data "aws_iam_policy_document" "cost_report_assume_role" {
  count = local.cost_monitoring_enabled

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cost_report" {
  count = local.cost_monitoring_enabled

  name               = "${local.name_prefix}-cost-report"
  assume_role_policy = data.aws_iam_policy_document.cost_report_assume_role[0].json
  tags               = merge(local.common_tags, { Service = "cost-report" })
}

# Cost Explorer is a global service whose ARNs are not resource-scoped, so
# ce:GetCostAndUsage cannot be narrowed below "*". The SES statement is
# narrowed to the one verified identity that sends the report, which is where
# the real blast radius would otherwise be.
data "aws_iam_policy_document" "cost_report" {
  count = local.cost_monitoring_enabled

  statement {
    sid       = "ReadCostExplorer"
    actions   = ["ce:GetCostAndUsage"]
    resources = ["*"]
  }

  statement {
    sid     = "SendReportEmail"
    actions = ["ses:SendEmail"]
    resources = [
      "arn:aws:ses:${var.aws_region}:${var.aws_account_id}:identity/${var.cost_report_sender_address}",
    ]
  }
}

resource "aws_iam_policy" "cost_report" {
  count = local.cost_monitoring_enabled

  name   = "${local.name_prefix}-cost-report"
  policy = data.aws_iam_policy_document.cost_report[0].json
  tags   = merge(local.common_tags, { Service = "cost-report" })
}

resource "aws_iam_role_policy_attachment" "cost_report" {
  count = local.cost_monitoring_enabled

  role       = aws_iam_role.cost_report[0].name
  policy_arn = aws_iam_policy.cost_report[0].arn
}

resource "aws_iam_role_policy_attachment" "cost_report_logs" {
  count = local.cost_monitoring_enabled

  role       = aws_iam_role.cost_report[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "cost_report" {
  count = local.cost_monitoring_enabled

  function_name    = "${local.name_prefix}-cost-report"
  role             = aws_iam_role.cost_report[0].arn
  filename         = data.archive_file.cost_report[0].output_path
  source_code_hash = data.archive_file.cost_report[0].output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.12"

  # Cost Explorer is slow and paginates; the default 3s times out on a full
  # month-to-date query long before the report is assembled.
  timeout     = 60
  memory_size = 256

  environment {
    variables = {
      PROJECT_TAG           = var.project_name
      SERVICE_TAG_KEY       = "Service"
      REPORT_SENDER_ADDRESS = var.cost_report_sender_address
      REPORT_RECIPIENTS     = join(",", var.cost_report_recipients)
      MONTHLY_BUDGET_USD    = tostring(var.monthly_budget_usd)
    }
  }

  tags = merge(local.common_tags, { Service = "cost-report" })
}

resource "aws_cloudwatch_event_rule" "weekly_cost_report" {
  count = local.cost_monitoring_enabled

  name = "${local.name_prefix}-weekly-cost-report"
  # Monday 08:00 UTC, matching the daily scholarship-matcher slot so the two
  # scheduled jobs stay easy to reason about together.
  schedule_expression = "cron(0 8 ? * MON *)"
  description         = "Weekly GOA AWS cost report by service tag."
  tags                = merge(local.common_tags, { Service = "cost-report" })
}

resource "aws_cloudwatch_event_target" "weekly_cost_report" {
  count = local.cost_monitoring_enabled

  rule      = aws_cloudwatch_event_rule.weekly_cost_report[0].name
  target_id = "cost-report-lambda"
  arn       = aws_lambda_function.cost_report[0].arn
}

resource "aws_lambda_permission" "weekly_cost_report" {
  count = local.cost_monitoring_enabled

  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_report[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_cost_report[0].arn
}
