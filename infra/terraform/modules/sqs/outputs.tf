output "queue_urls" {
  description = "SQS queue URLs by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.this :
    key => queue.url
  }
}

output "queue_arns" {
  description = "SQS queue ARNs by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.this :
    key => queue.arn
  }
}

output "queue_names" {
  description = "SQS queue names by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.this :
    key => queue.name
  }
}

output "dlq_urls" {
  description = "SQS DLQ URLs by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.dlq :
    key => queue.url
  }
}

output "dlq_arns" {
  description = "SQS DLQ ARNs by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.dlq :
    key => queue.arn
  }
}

output "dlq_names" {
  description = "SQS DLQ names by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.dlq :
    key => queue.name
  }
}

output "redrive_policies" {
  description = "Redrive policies by logical queue key."
  value = {
    for key, queue in aws_sqs_queue.this :
    key => queue.redrive_policy
  }
}

output "queue_contract" {
  description = "Queue contract passed into the module."
  value       = var.queues
}
