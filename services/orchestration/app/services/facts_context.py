"""Loading a user's long-term facts onto the chat critical path (GOA-038).

Extraction is deliberately off the request path. Reading is not -- the whole
point is that the assistant already knows you when you come back, which means a
database round trip in front of a classification call that already costs 3-8s.

Small, but it must never be able to fail a turn. Shaped after
app/services/exam_context.py, which established the pattern for this service:
cache in Redis, degrade to None on anything going wrong, and let the caller
carry on without the enrichment. A user whose facts are briefly unavailable gets
a slightly less personal answer. A user whose facts query raised gets nothing at
all, which is a far worse trade.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import structlog
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.core.metrics import (
    goa_orchestration_facts_load_latency_ms,
    goa_orchestration_facts_loaded_total,
)
from app.repositories.facts_repository import FactsRepository
from app.schemas.facts import StoredFact

logger = structlog.get_logger("orchestration.facts_context")

CACHE_KEY_PREFIX = "user_facts:"


def cache_key(user_id: str) -> str:
    return f"{CACHE_KEY_PREFIX}{user_id}"


async def invalidate_facts_cache(redis: AsyncRedis, user_id: str) -> None:
    """Drop a user's cached facts after a write or an erasure.

    Called by the sweep and by the delete endpoint. Without it, a five-minute
    window exists in which the assistant answers from a version of the user
    that no longer exists -- most visibly right after someone asks to be
    forgotten.
    """
    try:
        await redis.delete(cache_key(user_id))
    except Exception as e:
        logger.warning("Failed to invalidate facts cache", user_id=user_id, error=str(e))


async def fetch_user_facts(
    pool, redis: AsyncRedis, user_id: str
) -> Optional[list[StoredFact]]:
    """This user's live facts, or None if they could not be loaded.

    None and [] mean different things and the caller must not conflate them:
    [] is "we know this user and they have told us nothing durable", None is
    "we could not find out". Both produce the same prompt today; only one is a
    reason to look at a dashboard.
    """
    if not settings.memory_enabled:
        return None

    start = time.perf_counter()
    try:
        cached = await redis.get(cache_key(user_id))
        if cached is not None:
            facts = [StoredFact(**row) for row in json.loads(cached)]
            goa_orchestration_facts_loaded_total.labels(source="cache").inc()
            goa_orchestration_facts_load_latency_ms.observe(
                (time.perf_counter() - start) * 1000
            )
            return facts
    except Exception as e:
        # A broken cache entry is not a reason to skip the database.
        logger.warning("Facts cache read failed", user_id=user_id, error=str(e))

    if pool is None:
        goa_orchestration_facts_loaded_total.labels(source="miss").inc()
        return None

    try:
        repo = FactsRepository(pool)
        facts = await asyncio.wait_for(
            repo.get_live_facts(user_id, settings.memory_fact_ttl_days),
            timeout=settings.memory_load_timeout_ms / 1000,
        )
    except asyncio.TimeoutError:
        # A hard ceiling rather than a hope. Postgres degrading must cost the
        # personalisation, never the answer.
        goa_orchestration_facts_loaded_total.labels(source="miss").inc()
        logger.warning(
            "Fact load exceeded its budget - continuing without long-term memory",
            user_id=user_id,
            budget_ms=settings.memory_load_timeout_ms,
        )
        return None
    except Exception as e:
        goa_orchestration_facts_loaded_total.labels(source="miss").inc()
        logger.warning("Failed to load user facts", user_id=user_id, error=str(e))
        return None

    try:
        await redis.set(
            cache_key(user_id),
            json.dumps([f.model_dump() for f in facts]),
            ex=settings.memory_cache_ttl_seconds,
        )
    except Exception as e:
        logger.warning("Failed to cache user facts", user_id=user_id, error=str(e))

    goa_orchestration_facts_loaded_total.labels(source="db").inc()
    goa_orchestration_facts_load_latency_ms.observe((time.perf_counter() - start) * 1000)
    return facts
