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
      alltrue([
        for required_key in ["user_events", "notification", "ingestion"] :
        contains(keys(var.queues), required_key)
      ]) &&
      endswith(var.queues.user_events.name, "user-events") &&
      endswith(var.queues.notification.name, "notification-queue") &&
      endswith(var.queues.ingestion.name, "ingestion-queue") &&
      alltrue([
        for key, queue in var.queues :
        startswith(key, "user_events_") ? startswith(queue.name, "${var.name_prefix}-user-events-") : true
      ])
    )
    error_message = "GOA requires user-events, notification-queue, ingestion-queue, and AccountDeleted subscriber queues to follow the user-events-* naming contract."
  }

  validation {
    condition = (
      var.queues.user_events.visibility_timeout_seconds == 30 &&
      var.queues.notification.visibility_timeout_seconds == 30 &&
      var.queues.ingestion.visibility_timeout_seconds >= 900 &&
      alltrue([
        for queue in values(var.queues) : queue.max_receive_count == 3
      ]) &&
      alltrue([
        for key, queue in var.queues :
        startswith(key, "user_events_") ? queue.visibility_timeout_seconds == 30 : true
      ])
    )
    error_message = "Interactive queues require a 30-second visibility timeout; ingestion requires at least 900 seconds; every queue requires max_receive_count = 3."
  }
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
