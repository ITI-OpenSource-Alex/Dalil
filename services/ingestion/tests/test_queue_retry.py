import handler


class _SQS:
    def __init__(self):
        self.sent = []

    def receive_message(self, **kwargs):
        self.received = kwargs
        return {
            "Messages": [
                {
                    "Body": '{"dry_run": true}',
                    "ReceiptHandle": "receipt-1",
                }
            ]
        }

    def delete_message(self, **kwargs):
        self.deleted = kwargs


def test_queue_consumer_deletes_only_a_successful_message(monkeypatch):
    sqs = _SQS()
    monkeypatch.setenv("INGESTION_QUEUE_URL", "queue-url")
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: sqs)
    run = []
    monkeypatch.setattr(handler, "handle_ingestion", lambda event: run.append(event))

    handler.consume_queue(once=True)

    assert run == [{"dry_run": True}]
    assert sqs.deleted["ReceiptHandle"] == "receipt-1"
    assert sqs.received["VisibilityTimeout"] == 4320


def test_queue_consumer_leaves_failed_message_for_redrive(monkeypatch):
    sqs = _SQS()
    monkeypatch.setenv("INGESTION_QUEUE_URL", "queue-url")
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: sqs)

    def fail(_event):
        raise RuntimeError("source blocked")

    monkeypatch.setattr(handler, "handle_ingestion", fail)
    handler.consume_queue(once=True)

    assert not hasattr(sqs, "deleted")
