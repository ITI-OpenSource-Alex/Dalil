resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = var.role_arn
  package_type  = var.package_type
  image_uri     = var.package_type == "Image" ? var.image_uri : null
  filename  = var.package_type == "Zip" ? var.filename : null
  handler   = var.package_type == "Zip" ? var.handler : null
  runtime   = var.package_type == "Zip" ? var.runtime : null

  timeout     = var.timeout
  memory_size = var.memory_size

  # -1 means "unreserved" to Terraform's aws_lambda_function resource; the
  # actual arg AWS expects is simply omitted in that case.
  
  reserved_concurrent_executions = var.reserved_concurrent_executions

  layers = (
    var.package_type == "Zip" && var.enable_lambda_insights
    ? [var.lambda_insights_layer_arn]
    : []
  )

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_security_group_ids
  }

  layers = [var.lambda_insights_layer_arn]

  dynamic "tracing_config" {
    for_each = var.enable_tracing ? [1] : []
    content {
      mode = "Active"
    }
  }

  environment {
    variables = var.environment_variables
  }

  tags = var.tags
}
