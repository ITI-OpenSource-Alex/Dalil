variable "name_prefix" {
  description = "Name prefix for SQS resources."
  type        = string
}

variable "queues" {
  description = "Queue definitions with DLQ redrive settings."
  type = map(object({
    name                       = string
    visibility_timeout_seconds = number
    max_receive_count          = number
  }))

  validation {
    condition = (
      length(var.queues) == 3 &&
      length(setsubtract(
        toset(["user-events", "notification-queue", "ingestion-queue"]),
        toset([for queue in values(var.queues) : queue.name])
      )) == 0
    )
    error_message = "GOA-070 requires exactly these SQS queues: user-events, notification-queue, ingestion-queue."
  }

  validation {
    condition = alltrue([
      for queue in values(var.queues) :
      queue.visibility_timeout_seconds == 30 && queue.max_receive_count == 3
    ])
    error_message = "GOA-070 requires every SQS queue to use visibility_timeout_seconds = 30 and max_receive_count = 3."
  }
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
