import asyncio
from unittest.mock import AsyncMock

import pytest

from app import main


@pytest.mark.asyncio
async def test_lifespan_cleans_up_when_background_consumer_fails(monkeypatch):
    async def failed_consumer():
        raise RuntimeError("consumer startup failed")

    connect_db = AsyncMock()
    disconnect_db = AsyncMock()
    connect_redis = AsyncMock()
    disconnect_redis = AsyncMock()

    monkeypatch.setattr(main.db, "connect", connect_db)
    monkeypatch.setattr(main.db, "disconnect", disconnect_db)
    monkeypatch.setattr(main.redis_client, "connect", connect_redis)
    monkeypatch.setattr(main.redis_client, "disconnect", disconnect_redis)
    monkeypatch.setattr(main, "consume_sqs_messages", failed_consumer)

    async with main.lifespan(main.app):
        await asyncio.sleep(0)

    connect_db.assert_awaited_once()
    connect_redis.assert_awaited_once()
    disconnect_db.assert_awaited_once()
    disconnect_redis.assert_awaited_once()
