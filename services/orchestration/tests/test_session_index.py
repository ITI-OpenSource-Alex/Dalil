"""GOA-038 -- the session activity index, against a real Redis.

Real Redis, not a mock, for the same reason the repository tests use real
Postgres: the behaviour under test *is* the data structure. `idle_sessions` is a
ZRANGEBYSCORE; a MagicMock that returns a list would prove only that the test
author can write a list.

Runs against db 9 so a developer's live stack in db 1 is never touched.

    docker compose up -d redis-cache
    docker compose run --rm --entrypoint "python -m pytest tests/test_session_index.py -v" orchestration
"""

import json
import os
import time
import uuid

import pytest
import pytest_asyncio
from redis.asyncio import Redis as AsyncRedis

from app.services import session_index as si


def _test_redis_url() -> str:
    """The configured Redis, forced onto db 9."""
    url = os.environ["REDIS_URL"]
    base, _, _ = url.rpartition("/")
    return f"{base}/9"


@pytest_asyncio.fixture
async def redis():
    try:
        client = AsyncRedis.from_url(_test_redis_url(), decode_responses=True)
        await client.ping()
    except Exception as exc:  # noqa: BLE001 - the message is the point
        pytest.fail(
            f"Could not reach Redis at {_test_redis_url()!r} ({exc}). These tests need a "
            "real Redis by design. Start one with `docker compose up -d redis-cache`."
        )
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.fixture
def session_id():
    return f"s-{uuid.uuid4()}"


@pytest.fixture
def user_id():
    return f"u-{uuid.uuid4()}"


async def seed_history(redis, session_id, turns):
    """Write a transcript the way RedisChatMessageHistory does: LPUSH, newest first."""
    for role, content in turns:
        await redis.lpush(
            si.history_key(session_id),
            json.dumps({"type": role, "data": {"content": content}}),
        )


# ------------------------------------------------------------------ indexing


async def test_touch_records_owner_and_activity(redis, session_id, user_id):
    await si.touch_session(redis, session_id, user_id)

    meta = await si.session_meta(redis, session_id)
    assert meta["user_id"] == user_id
    assert meta["turns"] == 1
    assert time.time() - meta["last_activity_at"] < 5


async def test_touch_counts_turns_and_moves_the_clock(redis, session_id, user_id):
    await si.touch_session(redis, session_id, user_id)
    first = await si.session_meta(redis, session_id)

    await si.touch_session(redis, session_id, user_id)
    await si.touch_session(redis, session_id, user_id)
    later = await si.session_meta(redis, session_id)

    assert later["turns"] == 3
    assert later["last_activity_at"] >= first["last_activity_at"]


async def test_touch_sets_a_ttl_matching_the_transcript(redis, session_id, user_id):
    """An index entry outliving the transcript would point the sweep at nothing."""
    await si.touch_session(redis, session_id, user_id)

    ttl = await redis.ttl(si.session_key(session_id))
    assert 0 < ttl <= si.SESSION_TTL_SECONDS


async def test_session_meta_is_none_when_the_entry_expired(redis, session_id):
    assert await si.session_meta(redis, session_id) is None


# ------------------------------------------------------------- idle detection


async def test_idle_sessions_finds_only_quiet_ones(redis, user_id):
    quiet, busy = f"s-{uuid.uuid4()}", f"s-{uuid.uuid4()}"
    await si.touch_session(redis, quiet, user_id)
    await si.touch_session(redis, busy, user_id)
    # Backdate rather than sleep: the threshold is 30 minutes in production, and
    # a test that waits it out is a test nobody runs.
    await redis.zadd(si.ACTIVE_SESSIONS_KEY, {quiet: time.time() - 3600})

    idle = await si.idle_sessions(redis, time.time() - 1800, limit=10)

    assert idle == [quiet]


async def test_idle_sessions_returns_oldest_first_and_respects_the_limit(redis, user_id):
    """The limit is the cost control: each candidate is a frontier-model call."""
    now = time.time()
    ids = [f"s-{i}-{uuid.uuid4()}" for i in range(5)]
    for offset, sid in enumerate(ids):
        await si.touch_session(redis, sid, user_id)
        await redis.zadd(si.ACTIVE_SESSIONS_KEY, {sid: now - 3600 - (5 - offset)})

    idle = await si.idle_sessions(redis, now - 1800, limit=2)

    assert idle == ids[:2]


async def test_drop_from_active_keeps_the_metadata(redis, session_id, user_id):
    """A swept session that resumes must keep its turn count, not restart at 1."""
    await si.touch_session(redis, session_id, user_id)

    await si.drop_from_active(redis, session_id)

    assert await si.idle_sessions(redis, time.time() + 1, limit=10) == []
    assert (await si.session_meta(redis, session_id))["turns"] == 1


async def test_a_resumed_session_becomes_a_candidate_again(redis, session_id, user_id):
    await si.touch_session(redis, session_id, user_id)
    await si.drop_from_active(redis, session_id)

    await si.touch_session(redis, session_id, user_id)

    assert await si.idle_sessions(redis, time.time() + 1, limit=10) == [session_id]


# ---------------------------------------------------------------- transcripts


async def test_read_user_turns_ignores_assistant_messages(redis, session_id):
    """Extraction sources the user, never the system's own suggestions.

    Without this filter a RAG answer that suggests TU Munich becomes a
    'mentioned program' the user never said -- the system would be remembering
    itself talking.
    """
    await seed_history(
        redis,
        session_id,
        [
            ("human", "I studied electrical engineering"),
            ("ai", "Have you considered TU Munich?"),
            ("human", "My GPA is 3.2"),
        ],
    )

    turns = await si.read_user_turns(redis, session_id)

    assert turns == ["I studied electrical engineering", "My GPA is 3.2"]


async def test_read_user_turns_survives_a_corrupt_entry(redis, session_id):
    await redis.lpush(si.history_key(session_id), "not json at all")
    await seed_history(redis, session_id, [("human", "still readable")])

    assert await si.read_user_turns(redis, session_id) == ["still readable"]


async def test_read_user_turns_is_empty_for_an_unknown_session(redis, session_id):
    assert await si.read_user_turns(redis, session_id) == []


# ------------------------------------------------------------------- erasure


async def test_forget_user_sessions_erases_every_trace(redis, user_id):
    """The short-term half of 'forget everything about me'."""
    sessions = [f"s-{uuid.uuid4()}" for _ in range(3)]
    for sid in sessions:
        await si.touch_session(redis, sid, user_id)
        await seed_history(redis, sid, [("human", "something personal")])

    cleared = await si.forget_user_sessions(redis, user_id)

    assert cleared == 3
    for sid in sessions:
        assert await redis.exists(si.history_key(sid)) == 0
        assert await redis.exists(si.session_key(sid)) == 0
    assert await si.idle_sessions(redis, time.time() + 1, limit=10) == []
    assert await redis.exists(si.user_sessions_key(user_id)) == 0


async def test_forget_user_sessions_leaves_other_users_alone(redis, user_id):
    other = f"u-{uuid.uuid4()}"
    mine, theirs = f"s-{uuid.uuid4()}", f"s-{uuid.uuid4()}"
    await si.touch_session(redis, mine, user_id)
    await si.touch_session(redis, theirs, other)
    await seed_history(redis, theirs, [("human", "their private message")])

    await si.forget_user_sessions(redis, user_id)

    assert await redis.exists(si.session_key(theirs)) == 1
    assert await si.read_user_turns(redis, theirs) == ["their private message"]


async def test_forget_user_sessions_is_idempotent(redis, user_id):
    await si.touch_session(redis, f"s-{uuid.uuid4()}", user_id)

    assert await si.forget_user_sessions(redis, user_id) == 1
    assert await si.forget_user_sessions(redis, user_id) == 0
