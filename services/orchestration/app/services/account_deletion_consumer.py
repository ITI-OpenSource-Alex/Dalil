from __future__ import annotations

import asyncio

import structlog
from aiobotocore.session import get_session
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.services.account_deletion import parse_account_deleted_event, purge_user_data

logger = structlog.get_logger("orchestration.account_deletion_consumer")


async def consume_account_deleted_messages() -> None:
    session = get_session()
    client_options = {
        "region_name": settings.aws_region,
        "endpoint_url": settings.aws_endpoint_url or None,
    }
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_options["aws_access_key_id"] = settings.aws_access_key_id
        client_options["aws_secret_access_key"] = settings.aws_secret_access_key

    async with session.create_client("sqs", **client_options) as sqs_client:
        try:
            response = await sqs_client.get_queue_url(QueueName=settings.sqs_queue_name)
            queue_url = response["QueueUrl"]
        except (BotoCoreError, ClientError) as exc:
            logger.warning("AccountDeleted queue unavailable", error=str(exc))
            return

        while True:
            try:
                response = await sqs_client.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20,
                )
                for message in response.get("Messages", []):
                    user_id = parse_account_deleted_event(message["Body"])
                    if user_id:
                        await purge_user_data(user_id)
                    await sqs_client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message["ReceiptHandle"],
                    )
            except asyncio.CancelledError:
                logger.info("AccountDeleted consumer stopped")
                break
            except Exception as exc:
                logger.error("AccountDeleted consumer receive failed", error=str(exc))
                await asyncio.sleep(5)
