"""
Exam Context Service — GOA-061

Fetches and caches the user's exam profile from the Exam microservice.
The profile powers: prompt injection into the Supervisor Agent, opportunity
scoring band overrides, and the EXAM_PREP intent's personalised responses.

Cache strategy:
    Key:  exam_context:{user_id}
    TTL:  1800 s (30 minutes)
    Miss: GET /internal/users/{user_id}/profile-for-recommendation
"""

import json
from typing import Optional

import httpx
import structlog
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

logger = structlog.get_logger("orchestration.exam_context")

CACHE_TTL_SECONDS = 1800  # 30 minutes
CACHE_KEY_PREFIX = "exam_context"


def _cache_key(user_id: str) -> str:
    return f"{CACHE_KEY_PREFIX}:{user_id}"


async def get_redis_client() -> AsyncRedis:
    """Create a lightweight async Redis client reusing the same URL as memory.py."""
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)


async def fetch_exam_context(
    http_client: httpx.AsyncClient,
    user_id: str,
    redis_client: Optional[AsyncRedis] = None,
) -> Optional[dict]:
    """
    Return the user's exam profile, preferring a warm Redis cache.

    Returns ``None`` on any failure (network, timeout, invalid JSON) so the
    caller can gracefully degrade — the profile is enrichment, not a gate.

    Response shape (from Exam Service ``RecommendationProfile``):
        {
            "exam_count": int,
            "latest_bands": {"reading": 6.5, ...} | null,
            "weak_areas": {"speaking": "pronunciation", ...} | null,
            "last_exam_date": "2025-07-20T..." | null
        }
    """

    owns_redis = redis_client is None
    try:
        if owns_redis:
            redis_client = await get_redis_client()

        # ---------- 1. Try cache first ----------
        cached = await redis_client.get(_cache_key(user_id))
        if cached is not None:
            logger.debug("Exam context cache hit", user_id=user_id)
            return json.loads(cached)

        # ---------- 2. Cache miss → call Exam Service ----------
        url = (
            f"{settings.exam_service_url}"
            f"/internal/users/{user_id}/profile-for-recommendation"
        )
        headers = {"X-Internal-API-Key": settings.internal_api_key}

        logger.info("Fetching exam context from Exam Service", user_id=user_id, url=url)
        response = await http_client.get(url, headers=headers)
        response.raise_for_status()

        profile: dict = response.json()

        # ---------- 3. Warm the cache ----------
        await redis_client.set(
            _cache_key(user_id),
            json.dumps(profile),
            ex=CACHE_TTL_SECONDS,
        )
        logger.info(
            "Exam context cached",
            user_id=user_id,
            exam_count=profile.get("exam_count", 0),
        )
        return profile

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Exam Service returned an error status",
            user_id=user_id,
            status_code=exc.response.status_code,
        )
        return None

    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        logger.warning(
            "Failed to reach Exam Service",
            user_id=user_id,
            error=str(exc),
        )
        return None

    except Exception as exc:
        logger.error(
            "Unexpected error fetching exam context",
            user_id=user_id,
            error=str(exc),
        )
        return None

    finally:
        if owns_redis and redis_client is not None:
            await redis_client.aclose()
