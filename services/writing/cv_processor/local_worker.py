import json
import logging
import time

from app.config import get_settings
from cv_processor.handler import _aws_client, lambda_handler


logger = logging.getLogger("writing.cv_processor.local_worker")
QUEUE_RETRY_DELAY_SECONDS = 2


def _poll_once(sqs, queue_url: str) -> None:
    response = sqs.receive_message(
        QueueUrl=queue_url,
        WaitTimeSeconds=20,
        MaxNumberOfMessages=1,
    )
    for message in response.get("Messages", []):
        try:
            lambda_handler(json.loads(message["Body"]), None)
        except Exception:
            logger.exception("Local CV processor message failed")
            time.sleep(1)
            continue
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )


def run(
    *,
    max_polls: int | None = None,
    retry_delay_seconds: float = QUEUE_RETRY_DELAY_SECONDS,
) -> None:
    settings = get_settings()
    if not settings.cv_processor_queue_url:
        raise RuntimeError("CV_PROCESSOR_QUEUE_URL is not configured")
    sqs = _aws_client("sqs", settings)
    logger.info("Local CV processor is polling %s", settings.cv_processor_queue_url)

    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        try:
            _poll_once(sqs, settings.cv_processor_queue_url)
        except Exception:
            # LocalStack can be healthy before its init hook recreates this
            # queue. A temporary SQS outage must not terminate the worker and
            # leave every queued CV stuck in `processing`.
            logger.exception("CV processor queue poll failed; retrying")
            time.sleep(retry_delay_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
