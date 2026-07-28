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
      toset(keys(var.queues)) == toset(["user_events", "notification", "ingestion"]) &&
      endswith(var.queues.user_events.name, "user-events") &&
      endswith(var.queues.notification.name, "notification-queue") &&
      endswith(var.queues.ingestion.name, "ingestion-queue")
    )
    error_message = "GOA-070 requires exactly the user-events, notification-queue, and ingestion-queue definitions."
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
