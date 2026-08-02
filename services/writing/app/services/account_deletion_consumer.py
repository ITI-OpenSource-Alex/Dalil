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
            response = await asyncio.to_thread(
                sqs.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
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
