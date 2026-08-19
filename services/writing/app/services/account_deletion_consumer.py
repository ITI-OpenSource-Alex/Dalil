from __future__ import annotations

import asyncio
import logging
import os

import boto3

from app.database import SessionLocal
from app.services.account_deletion import parse_account_deleted_event, purge_user_data

logger = logging.getLogger(__name__)


def _sqs_client():
    return boto3.client(
        "sqs",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )


async def consume_account_deleted_messages() -> None:
    queue_url = os.getenv("ACCOUNT_DELETED_QUEUE_URL") or os.getenv("SQS_QUEUE_URL")
    if not queue_url:
        logger.warning("AccountDeleted queue not configured for writing service")
        return

    sqs = _sqs_client()
    while True:
        try:
            # WaitTimeSeconds bounds how long shutdown takes, not just how
            # often we poll.
            #
            # asyncio.to_thread cannot be cancelled once its thread is running:
            # task.cancel() marks the future, the poll runs to completion
            # regardless, and the event loop joins its default executor on
            # teardown. So shutdown is held for up to this value no matter what
            # the cancellation code in main.py looks like. At 20 that meant a
            # twenty-second container stop on every deploy, and -- because
            # TestClient runs the application lifespan per test -- twenty
            # seconds of teardown on every integration test in this service,
            # which read as a hung suite.
            #
            # Five keeps most of the benefit of long polling (an idle queue
            # costs one request per five seconds instead of one per loop) while
            # capping the stall at five. Raising it again means accepting that
            # shutdown latency.
            response = await asyncio.to_thread(
                sqs.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
            )
            for message in response.get("Messages", []):
                user_id = parse_account_deleted_event(message["Body"])
                if user_id:
                    db = SessionLocal()
                    try:
                        purge_user_data(db, user_id)
                    finally:
                        db.close()
                await asyncio.to_thread(
                    sqs.delete_message,
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
        except asyncio.CancelledError:
            logger.info("AccountDeleted consumer stopped")
            break
        except Exception as exc:
            logger.exception("AccountDeleted consumer receive failed: %s", exc)
            await asyncio.sleep(5)
