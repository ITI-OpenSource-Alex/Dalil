import json
import logging
import time

from app.config import get_settings
from cv_processor.handler import _aws_client, lambda_handler


logger = logging.getLogger("writing.cv_processor.local_worker")


def run() -> None:
    settings = get_settings()
    if not settings.cv_processor_queue_url:
        raise RuntimeError("CV_PROCESSOR_QUEUE_URL is not configured")
    sqs = _aws_client("sqs", settings)
    logger.info("Local CV processor is polling %s", settings.cv_processor_queue_url)

    while True:
        response = sqs.receive_message(
            QueueUrl=settings.cv_processor_queue_url,
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
                QueueUrl=settings.cv_processor_queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
