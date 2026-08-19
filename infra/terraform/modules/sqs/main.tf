resource "aws_sqs_queue" "dlq" {
  for_each = var.queues

  name                      = "${each.value.name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = merge(var.tags, {
    Name        = "${each.value.name}-dlq"
    QueueRole   = "dead-letter"
    SourceQueue = each.value.name
  })
}

resource "aws_sqs_queue" "this" {
  for_each = var.queues

  name                       = each.value.name
  visibility_timeout_seconds = each.value.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.max_receive_count
  })

  tags = merge(var.tags, {
    Name      = each.value.name
    QueueRole = "primary"
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "this" {
  for_each = var.queues

  queue_url = aws_sqs_queue.dlq[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this[each.key].arn]
  })
}
