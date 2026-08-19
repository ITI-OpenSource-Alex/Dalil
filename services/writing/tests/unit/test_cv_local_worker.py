import json
from types import SimpleNamespace

from cv_processor import local_worker


class FakeSqs:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.receive_calls = 0
        self.deleted = []

    def receive_message(self, **_kwargs):
        self.receive_calls += 1
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


def test_worker_retries_after_temporary_queue_failure(monkeypatch):
    sqs = FakeSqs([RuntimeError("queue does not exist yet"), {"Messages": []}])
    sleeps = []
    monkeypatch.setattr(
        local_worker,
        "get_settings",
        lambda: SimpleNamespace(cv_processor_queue_url="http://sqs/cv-processing"),
    )
    monkeypatch.setattr(local_worker, "_aws_client", lambda *_args: sqs)
    monkeypatch.setattr(local_worker.time, "sleep", sleeps.append)

    local_worker.run(max_polls=2, retry_delay_seconds=0.25)

    assert sqs.receive_calls == 2
    assert sleeps == [0.25]


def test_worker_deletes_message_only_after_successful_processing(monkeypatch):
    message = {
        "Body": json.dumps({"Records": []}),
        "ReceiptHandle": "receipt-1",
    }
    sqs = FakeSqs([{"Messages": [message]}])
    handled = []
    monkeypatch.setattr(
        local_worker,
        "get_settings",
        lambda: SimpleNamespace(cv_processor_queue_url="http://sqs/cv-processing"),
    )
    monkeypatch.setattr(local_worker, "_aws_client", lambda *_args: sqs)
    monkeypatch.setattr(
        local_worker,
        "lambda_handler",
        lambda event, _context: handled.append(event),
    )

    local_worker.run(max_polls=1)

    assert handled == [{"Records": []}]
    assert sqs.deleted == [
        {"QueueUrl": "http://sqs/cv-processing", "ReceiptHandle": "receipt-1"}
    ]
