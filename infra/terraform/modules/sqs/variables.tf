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
        for required_key in ["notification", "ingestion"] :
        contains(keys(var.queues), required_key)
      ]) &&
      endswith(var.queues.notification.name, "notification-queue") &&
      endswith(var.queues.ingestion.name, "ingestion-queue") &&
      alltrue([
        for subscriber in [
          "user_events_rag",
          "user_events_orchestration",
          "user_events_exam",
          "user_events_speaking",
          "user_events_writing",
          "user_events_notification",
        ] :
        contains(keys(var.queues), subscriber)
      ]) &&
      alltrue([
        for key, queue in var.queues :
        startswith(key, "user_events_") ? startswith(queue.name, "${var.name_prefix}-user-events-") : true
      ])
    )
    error_message = "GOA requires notification-queue, ingestion-queue, and all user-events subscriber queues to follow the naming contract."
  }

  validation {
    condition = (
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
