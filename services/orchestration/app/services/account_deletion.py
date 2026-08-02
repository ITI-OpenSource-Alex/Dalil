from __future__ import annotations

import json

import redis.asyncio as redis
import structlog

from app.core.config import settings

logger = structlog.get_logger("orchestration.account_deletion")


def parse_account_deleted_event(message_body: str | dict) -> str | None:
    event = json.loads(message_body) if isinstance(message_body, str) else message_body
    if event.get("Type") == "Notification" and event.get("Message"):
        event = json.loads(event["Message"])
    if event.get("type") != "account.deleted":
        return None
    return event.get("payload", {}).get("userId")


async def purge_user_data(user_id: str) -> int:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    deleted = 0
    try:
        patterns = [
            f"exam_context:{user_id}",
            f"llm:tokens:*:user:{user_id}:orchestration",
            f"message_store:*{user_id}*",
        ]
        for pattern in patterns:
            async for key in client.scan_iter(match=pattern):
                deleted += await client.delete(key)
        logger.info("Purged orchestration user data", user_id=user_id, deleted_keys=deleted)
        return deleted
    finally:
        await client.aclose()
