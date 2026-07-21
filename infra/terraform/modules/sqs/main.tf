resource "aws_sqs_queue" "dlq" {
  for_each = var.queues

  name                      = "${each.value.name}-dlq"
  message_retention_seconds = 1209600

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

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.max_receive_count
  })

  tags = merge(var.tags, {
    Name      = each.value.name
    QueueRole = "primary"
  })
}
