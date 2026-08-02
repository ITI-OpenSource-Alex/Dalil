"""Erasing what the service remembers about a user (GOA-038, AC 6).

Two halves, and both are required for the answer to be true:

- the long-term facts in orchestration_db, which is what the AC names;
- the short-term transcripts in Redis, which it does not.

Wiping only the first leaves the assistant still resolving "it" and "that one"
from the last ten turns of an open session. A user who has just asked to be
forgotten and watches that happen has been told something false, and the fact
that the remaining memory expires on its own in 24 hours is not an answer to
them.
"""

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.database import db
from app.repositories.facts_repository import FactsRepository
from app.services.facts_context import invalidate_facts_cache
from app.services.session_index import forget_user_sessions, get_redis_client

logger = structlog.get_logger("orchestration.api.memory")
router = APIRouter()


@router.delete("/sessions/memory")
async def delete_user_memory(
    req: Request,
    x_user_id: str = Header(None, alias="X-User-Id"),
):
    """Delete everything this service remembers about the calling user.

    The identity comes from the header the Gateway sets from a validated JWT,
    and from nowhere else. Accepting a user id from a body or a query parameter
    would let any authenticated user erase any other user's memory by typing
    their id -- a destructive, unauthenticated operation dressed as a privacy
    feature.

    Trusting X-User-Id is trusting the Gateway, which is the boundary this
    service already sits behind: every internal call carries INTERNAL_API_KEY
    and reaching this port directly is reaching past the front door. That is
    the existing trust model, not a new assumption made here.

    Idempotent: erasing nothing is a success, and returns zero.
    """
    correlation_id = getattr(req.state, "correlation_id", None)

    if not x_user_id or not x_user_id.strip():
        # 401 rather than 400: this is missing identity, not a malformed request.
        raise HTTPException(status_code=401, detail="X-User-Id header is required")

    user_id = x_user_id.strip()

    facts_deleted = 0
    if db.pool is not None:
        try:
            repo = FactsRepository(db.pool)
            facts_deleted = await repo.delete_all_for_user(user_id)
        except Exception as e:
            # A deletion that partially failed must not report success. This is
            # the one path in the feature where degrading quietly is wrong:
            # everywhere else a failure costs personalisation, here it would
            # tell someone their data is gone when it is not.
            logger.error(
                "Failed to delete long-term facts",
                user_id=user_id,
                correlation_id=correlation_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=500, detail="Failed to delete stored memory"
            ) from e
    else:
        logger.error(
            "Memory deletion requested with no database connection",
            user_id=user_id,
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=503, detail="Memory store unavailable")

    sessions_cleared = 0
    redis_client = None
    try:
        redis_client = await get_redis_client()
        sessions_cleared = await forget_user_sessions(redis_client, user_id)
        await invalidate_facts_cache(redis_client, user_id)
    except Exception as e:
        logger.error(
            "Failed to clear short-term session memory",
            user_id=user_id,
            correlation_id=correlation_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail="Failed to clear conversation history"
        ) from e
    finally:
        if redis_client is not None:
            await redis_client.aclose()

    # Structured privacy event, in the field shape GOA-034 defines for security
    # logging, so that ticket's queries find these without rework. No fact
    # values: this is a record that an erasure happened, and writing the erased
    # content into a log that ships to an aggregator would defeat the request.
    logger.info(
        "SECURITY_EVENT",
        event_type="user_memory_erased",
        severity="INFO",
        user_id=user_id,
        correlation_id=correlation_id,
        action_taken="deleted_facts_and_sessions",
        facts_deleted=facts_deleted,
        sessions_cleared=sessions_cleared,
    )

    return {
        "factsDeleted": facts_deleted,
        "sessionsCleared": sessions_cleared,
        "factRetentionDays": settings.memory_fact_ttl_days,
    }
