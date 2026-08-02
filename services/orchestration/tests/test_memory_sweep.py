"""GOA-038 -- the sweep, against real Postgres and real Redis.

Only the LLM is mocked. Everything else is the real thing: the candidate query
is a real ZRANGEBYSCORE, the lock is a real SET NX, and the facts land in a real
table with a real unique index. A fake for any of those would leave this file
asserting that its own fixtures behave the way its author imagined -- which is
precisely how a 262-line green test file once sat on top of a sweep that could
not write a single row.

Time is driven by backdating sorted-set scores, never by sleeping. The manual
E2E covers the other half of that, running the sweep with a real clock at
MEMORY_IDLE_MINUTES=1, because backdating a score proves the query and proves
nothing at all about whether the task was ever started.

    docker compose up -d postgres redis-cache
    docker compose run --rm --entrypoint "python -m pytest tests/test_memory_sweep.py -v" orchestration
"""

import os
import time
import uuid

import asyncpg
import pytest
import pytest_asyncio
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.repositories.facts_repository import FactsRepository
from app.schemas.facts import FactCandidate
from app.services import memory_sweep as sweep
from app.services import session_index as si
from app.services.fact_extraction import ExtractedFacts

IDLE_SECONDS = settings.memory_idle_minutes * 60


def _test_redis_url() -> str:
    url = os.environ["REDIS_URL"]
    base, _, _ = url.rpartition("/")
    return f"{base}/9"


@pytest_asyncio.fixture
async def redis():
    client = AsyncRedis.from_url(_test_redis_url(), decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"These tests need a real Redis ({exc}). `docker compose up -d redis-cache`.")
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def pool():
    from app.core.database import db

    try:
        await db.run_migrations()
        created = await asyncpg.create_pool(dsn=os.environ["DATABASE_URL"], min_size=1, max_size=5)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"These tests need a real Postgres ({exc}). `docker compose up -d postgres`.")
    try:
        yield created
    finally:
        await created.close()


@pytest.fixture
def user_id():
    return f"u-{uuid.uuid4()}"


@pytest_asyncio.fixture(autouse=True)
async def cleanup_facts(pool, user_id):
    yield
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_facts WHERE user_id LIKE 'u-%'")


class _FakeRaw:
    response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}


@pytest.fixture
def extraction(mocker):
    """Mock only the model call, and return a handle so tests can assert on it."""

    def _configure(parsed=None, side_effect=None):
        parsed = parsed or ExtractedFacts(
            degree="BSc in Electrical and Electronic Engineering",
            gpa=3.2,
            confidence=0.9,
        )
        stub = mocker.MagicMock()
        if side_effect is not None:
            stub.ainvoke = mocker.AsyncMock(side_effect=side_effect)
        else:
            stub.ainvoke = mocker.AsyncMock(
                return_value={"parsed": parsed, "raw": _FakeRaw()}
            )
        mocker.patch("app.services.fact_extraction.structured_extractor", stub)
        return stub.ainvoke

    return _configure


async def make_idle_session(redis, user_id, turns=4, idle_seconds=IDLE_SECONDS + 60, messages=None):
    """A session that has gone quiet, with a real transcript behind it."""
    import json

    session_id = f"s-{uuid.uuid4()}"
    for _ in range(turns):
        await si.touch_session(redis, session_id, user_id)
    for content in messages or ["I studied electrical engineering", "My GPA is 3.2"]:
        await redis.lpush(
            si.history_key(session_id),
            json.dumps({"type": "human", "data": {"content": content}}),
        )
    await redis.zadd(si.ACTIVE_SESSIONS_KEY, {session_id: time.time() - idle_seconds})
    return session_id


async def fact_rows(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT fact_type, fact_value, revision FROM user_facts WHERE user_id = $1 ORDER BY fact_type",
            user_id,
        )


# ------------------------------------------------------------- happy path


async def test_i06_idle_session_becomes_facts_in_postgres(pool, redis, user_id, extraction):
    """Asserted by reading the table, not by trusting the return value."""
    session_id = await make_idle_session(redis, user_id)
    extraction()

    result = await sweep.sweep_once(pool, redis)

    assert result.candidates == 1
    assert result.extracted == 1
    rows = await fact_rows(pool, user_id)
    assert {r["fact_type"] for r in rows} == {"degree", "gpa"}
    assert await si.idle_sessions(redis, time.time() + 1, 10) == [], "swept sessions leave the queue"
    assert session_id not in await si.idle_sessions(redis, time.time() + 1, 10)


async def test_i04_a_busy_session_is_not_swept(pool, redis, user_id, extraction):
    await make_idle_session(redis, user_id, idle_seconds=0)
    call = extraction()

    result = await sweep.sweep_once(pool, redis)

    assert result.candidates == 0
    call.assert_not_called()


async def test_i03_short_sessions_never_reach_the_model(pool, redis, user_id, extraction):
    """The cost control. An abandoned 'hi' must not buy a frontier-model call."""
    await make_idle_session(redis, user_id, turns=2)
    call = extraction()

    result = await sweep.sweep_once(pool, redis)

    assert result.skipped_short == 1
    call.assert_not_called()
    assert await si.idle_sessions(redis, time.time() + 1, 10) == [], (
        "a short session must be dropped, not reconsidered every five minutes for a day"
    )


async def test_i09_batch_cap_is_respected(pool, redis, user_id, extraction, monkeypatch):
    monkeypatch.setattr(settings, "memory_sweep_batch_max", 2)
    for _ in range(5):
        await make_idle_session(redis, user_id)
    call = extraction()

    result = await sweep.sweep_once(pool, redis)

    assert result.candidates == 2
    assert call.await_count == 2


async def test_sessions_with_no_transcript_are_skipped(pool, redis, user_id, extraction):
    session_id = f"s-{uuid.uuid4()}"
    for _ in range(4):
        await si.touch_session(redis, session_id, user_id)
    await redis.zadd(si.ACTIVE_SESSIONS_KEY, {session_id: time.time() - IDLE_SECONDS - 60})
    call = extraction()

    result = await sweep.sweep_once(pool, redis)

    assert result.skipped_missing == 1
    call.assert_not_called()


# ------------------------------------------------------------------ locking


async def test_i05_two_sweeps_racing_extract_once(pool, redis, user_id, extraction):
    """A second replica must not pay twice for the same session."""
    import asyncio

    await make_idle_session(redis, user_id)
    call = extraction()

    results = await asyncio.gather(
        sweep.sweep_once(pool, redis), sweep.sweep_once(pool, redis)
    )

    assert call.await_count == 1
    assert sum(r.extracted for r in results) == 1
    assert sum(r.locked_out for r in results) == 1


async def test_the_lock_is_released_after_a_successful_sweep(pool, redis, user_id, extraction):
    session_id = await make_idle_session(redis, user_id)
    extraction()

    await sweep.sweep_once(pool, redis)

    assert await redis.exists(f"{sweep.LOCK_PREFIX}{session_id}") == 0


# ------------------------------------------------------------ contradiction


async def test_i06b_a_later_session_updates_rather_than_duplicates(pool, redis, user_id, extraction):
    """The DoD's contradiction case, driven the way it actually happens."""
    await make_idle_session(redis, user_id)
    extraction(ExtractedFacts(gpa=3.2, confidence=0.9))
    await sweep.sweep_once(pool, redis)

    await make_idle_session(redis, user_id)
    extraction(ExtractedFacts(gpa=3.6, confidence=0.9))
    await sweep.sweep_once(pool, redis)

    rows = await fact_rows(pool, user_id)
    assert len(rows) == 1, "a corrected GPA is an update, not a second fact"
    assert rows[0]["fact_value"] == "3.6"
    assert rows[0]["revision"] == 2


# ------------------------------------------------------------ failure paths


async def test_i07_one_failure_does_not_abort_the_batch(pool, redis, user_id, extraction, mocker):
    await make_idle_session(redis, user_id)
    await make_idle_session(redis, user_id)
    await make_idle_session(redis, user_id)

    calls = {"n": 0}

    async def flaky(messages, config=None):
        calls["n"] += 1
        if calls["n"] <= 2:  # two attempts for the first session
            raise RuntimeError("gateway exploded")
        return {"parsed": ExtractedFacts(gpa=3.2, confidence=0.9), "raw": _FakeRaw()}

    stub = mocker.MagicMock()
    stub.ainvoke = flaky
    mocker.patch("app.services.fact_extraction.structured_extractor", stub)

    result = await sweep.sweep_once(pool, redis)

    assert result.errors == 1
    assert result.extracted == 2, "the other two sessions were still processed"


async def test_a_failed_session_stays_in_the_queue_for_the_next_tick(pool, redis, user_id, mocker):
    """Silently dropping a session on failure would lose its facts forever."""
    session_id = await make_idle_session(redis, user_id)
    stub = mocker.MagicMock()
    stub.ainvoke = mocker.AsyncMock(side_effect=RuntimeError("gateway exploded"))
    mocker.patch("app.services.fact_extraction.structured_extractor", stub)

    await sweep.sweep_once(pool, redis)

    assert await si.idle_sessions(redis, time.time() + 1, 10) == [session_id]


# --------------------------------------------------------------- expiry


async def test_i10_expired_facts_are_purged_in_the_same_tick(pool, redis, user_id, extraction):
    repo = FactsRepository(pool)
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="degree", fact_value="BSc EEE", confidence=0.9)
    )
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="target_country", fact_value="Germany", confidence=0.9)
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_facts SET reinforced_at = NOW() - INTERVAL '31 days' "
            "WHERE user_id = $1 AND fact_type = 'degree'",
            user_id,
        )

    await sweep.sweep_once(pool, redis)

    rows = await fact_rows(pool, user_id)
    assert [r["fact_type"] for r in rows] == ["target_country"]


# ----------------------------------------------------------- cache coupling


async def test_i11_the_request_path_cache_is_invalidated_after_a_write(
    pool, redis, user_id, extraction
):
    """Otherwise the next session answers from a version of the user that is now stale."""
    from app.services.facts_context import cache_key

    await redis.set(cache_key(user_id), "[]", ex=300)
    await make_idle_session(redis, user_id)
    extraction()

    await sweep.sweep_once(pool, redis)

    assert await redis.exists(cache_key(user_id)) == 0
