"""Which sessions exist, who owns them, and when they last moved (GOA-038).

None of this was recorded anywhere before. `userId` arrived on each request and
was dropped once the response finished, and the only per-session artefact in
Redis was LangChain's `message_store:{sessionId}` list -- which holds messages
and nothing else. The sweep needs both halves: facts are keyed by user, and
"idle for 30 minutes" is a question about time.

The list's TTL is technically a proxy for idleness, since RedisChatMessageHistory
refreshes it on every write (86400 - ttl_remaining = seconds since the last
turn). Building on that was rejected: it is an undocumented internal of
langchain_community 0.0.x that would break silently on any TTL change, and
finding the keys at all would mean scanning a Redis database shared with the
exam-context cache. So the write path records what the sweep needs, explicitly.

Everything here is best-effort. A failure to index a session costs that session's
facts; a failure that propagated would cost the user their answer.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

logger = structlog.get_logger("orchestration.session_index")

# LangChain owns this prefix (RedisChatMessageHistory.key_prefix). It is
# referenced here rather than re-declared in each caller so that a version bump
# that changes it has exactly one place to be fixed.
CHAT_HISTORY_PREFIX = "message_store:"

SESSION_KEY_PREFIX = "orch:session:"
ACTIVE_SESSIONS_KEY = "orch:sessions:active"
USER_SESSIONS_PREFIX = "orch:user:"

# Matches the chat history's own TTL. An entry that outlived the transcript it
# describes would send the sweep to read an empty list.
SESSION_TTL_SECONDS = 86400


def session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def user_sessions_key(user_id: str) -> str:
    return f"{USER_SESSIONS_PREFIX}{user_id}:sessions"


def history_key(session_id: str) -> str:
    return f"{CHAT_HISTORY_PREFIX}{session_id}"


async def get_redis_client() -> AsyncRedis:
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)


async def touch_session(redis: AsyncRedis, session_id: str, user_id: str) -> None:
    """Record that this session just moved, and who owns it.

    Called after the response has finished streaming, never before -- this is
    bookkeeping, and it must not sit between the user and their first token.

    The reverse index (user -> sessions) exists for the deletion path: "forget
    everything about me" has to reach the short-term transcripts too, and
    without this there would be no way to find them short of scanning the
    keyspace.
    """
    now = time.time()
    pipe = redis.pipeline()
    pipe.hset(
        session_key(session_id),
        mapping={"userId": user_id, "lastActivityAt": now},
    )
    pipe.hincrby(session_key(session_id), "turns", 1)
    pipe.expire(session_key(session_id), SESSION_TTL_SECONDS)
    pipe.zadd(ACTIVE_SESSIONS_KEY, {session_id: now})
    pipe.sadd(user_sessions_key(user_id), session_id)
    pipe.expire(user_sessions_key(user_id), SESSION_TTL_SECONDS)
    await pipe.execute()


async def idle_sessions(
    redis: AsyncRedis, older_than_epoch: float, limit: int
) -> list[str]:
    """Sessions whose last turn is older than the cutoff, oldest first.

    A sorted-set range rather than a keyspace scan: Redis db 1 is shared with
    the exam-context cache and LangChain's transcripts, and KEYS over a shared
    database is how a background job takes a service down at the worst moment.
    """
    return await redis.zrangebyscore(
        ACTIVE_SESSIONS_KEY, min="-inf", max=older_than_epoch, start=0, num=limit
    )


async def session_meta(redis: AsyncRedis, session_id: str) -> Optional[dict]:
    """Owner and turn count, or None if the entry has expired out from under us."""
    raw = await redis.hgetall(session_key(session_id))
    if not raw or not raw.get("userId"):
        return None
    try:
        turns = int(raw.get("turns", 0))
    except (TypeError, ValueError):
        turns = 0
    return {
        "user_id": raw["userId"],
        "turns": turns,
        "last_activity_at": float(raw.get("lastActivityAt", 0) or 0),
    }


async def read_user_turns(redis: AsyncRedis, session_id: str) -> list[str]:
    """The user's own messages from a session, oldest first.

    Only the user's turns. An assistant message mentioning TU Munich is not the
    user mentioning TU Munich, and extracting from both would fabricate facts
    out of the system's own suggestions.

    RedisChatMessageHistory LPUSHes, so the list is newest-first and gets
    reversed here.
    """
    import json

    raw = await redis.lrange(history_key(session_id), 0, -1)
    turns: list[str] = []
    for item in reversed(raw):
        try:
            message = json.loads(item)
        except (TypeError, ValueError):
            continue
        if message.get("type") != "human":
            continue
        content = (message.get("data") or {}).get("content")
        if content:
            turns.append(str(content))
    return turns


async def drop_from_active(redis: AsyncRedis, session_id: str) -> None:
    """Stop considering this session for extraction.

    Not a deletion: the metadata hash stays so a resumed session keeps its turn
    count, and the next turn re-adds it to the active set with a fresh score.
    """
    await redis.zrem(ACTIVE_SESSIONS_KEY, session_id)


async def forget_user_sessions(redis: AsyncRedis, user_id: str) -> int:
    """Erase every short-term trace of a user: transcripts, metadata, index.

    The long-term half of "forget me" is a DELETE against user_facts. This is
    the other half, and it is here because a user who asks to be forgotten and
    then watches the assistant resolve "it" from the last ten turns has been
    told something untrue.

    Returns the number of sessions cleared.
    """
    session_ids = await redis.smembers(user_sessions_key(user_id))
    if not session_ids:
        return 0

    pipe = redis.pipeline()
    for session_id in session_ids:
        pipe.delete(history_key(session_id))
        pipe.delete(session_key(session_id))
        pipe.zrem(ACTIVE_SESSIONS_KEY, session_id)
    pipe.delete(user_sessions_key(user_id))
    await pipe.execute()

    logger.info(
        "Cleared short-term session memory", user_id=user_id, sessions=len(session_ids)
    )
    return len(session_ids)
