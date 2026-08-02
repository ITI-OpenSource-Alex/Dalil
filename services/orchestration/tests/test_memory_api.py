"""GOA-038 -- DELETE /sessions/memory, against real Postgres and real Redis.

The interesting tests here are the ones about *whose* memory gets erased. A
delete endpoint that works is easy; a delete endpoint that cannot be pointed at
someone else is the requirement.
"""

import json
import os
import uuid

import asyncpg
import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis as AsyncRedis

from app.repositories.facts_repository import FactsRepository
from app.schemas.facts import FactCandidate
from app.services import session_index as si
from app.services.facts_context import cache_key


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


@pytest_asyncio.fixture
async def api(pool, redis, mocker):
    """The real app with a live pool, and Redis pointed at the test database."""
    from app.core import database
    from app.main import app

    mocker.patch.object(database.db, "pool", pool)
    mocker.patch(
        "app.api.memory.get_redis_client",
        mocker.AsyncMock(return_value=AsyncRedis.from_url(_test_redis_url(), decode_responses=True)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def user_id():
    return f"u-{uuid.uuid4()}"


@pytest_asyncio.fixture(autouse=True)
async def cleanup(pool):
    yield
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_facts WHERE user_id LIKE 'u-%'")


async def seed(pool, redis, user_id, sessions=2):
    repo = FactsRepository(pool)
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="degree", fact_value="BSc EEE", confidence=0.9)
    )
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="gpa", fact_value="3.2", confidence=0.9)
    )
    session_ids = []
    for _ in range(sessions):
        sid = f"s-{uuid.uuid4()}"
        await si.touch_session(redis, sid, user_id)
        await redis.lpush(
            si.history_key(sid),
            json.dumps({"type": "human", "data": {"content": "something personal"}}),
        )
        session_ids.append(sid)
    return session_ids


async def count_facts(pool, user_id) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM user_facts WHERE user_id = $1", user_id
        )


# ------------------------------------------------------------------- erasure


async def test_i16_delete_removes_facts_and_transcripts(api, pool, redis, user_id):
    """Q3's decision: both halves, or the answer given to the user is false."""
    sessions = await seed(pool, redis, user_id)

    response = await api.delete("/sessions/memory", headers={"X-User-Id": user_id})

    assert response.status_code == 200
    assert response.json()["factsDeleted"] == 2
    assert response.json()["sessionsCleared"] == 2
    assert await count_facts(pool, user_id) == 0
    for sid in sessions:
        assert await redis.exists(si.history_key(sid)) == 0, "the transcript is memory too"


async def test_delete_invalidates_the_request_path_cache(api, pool, redis, user_id):
    """Otherwise the assistant keeps answering from a profile that no longer exists."""
    await seed(pool, redis, user_id)
    await redis.set(cache_key(user_id), "[]", ex=300)

    await api.delete("/sessions/memory", headers={"X-User-Id": user_id})

    assert await redis.exists(cache_key(user_id)) == 0


async def test_i18_delete_is_idempotent(api, pool, redis, user_id):
    await seed(pool, redis, user_id)

    first = await api.delete("/sessions/memory", headers={"X-User-Id": user_id})
    second = await api.delete("/sessions/memory", headers={"X-User-Id": user_id})

    assert first.json()["factsDeleted"] == 2
    assert second.status_code == 200
    assert second.json()["factsDeleted"] == 0


# ------------------------------------------------------------------ identity


async def test_i17_no_identity_means_no_deletion(api, pool, redis, user_id):
    await seed(pool, redis, user_id)

    response = await api.delete("/sessions/memory")

    assert response.status_code == 401
    assert await count_facts(pool, user_id) == 2, "nothing may be deleted without an identity"


async def test_a_blank_identity_is_refused(api, pool, redis, user_id):
    await seed(pool, redis, user_id)

    response = await api.delete("/sessions/memory", headers={"X-User-Id": "   "})

    assert response.status_code == 401
    assert await count_facts(pool, user_id) == 2


async def test_erasure_is_scoped_to_the_calling_user(api, pool, redis, user_id):
    """The property that makes this endpoint safe to expose at all."""
    other = f"u-{uuid.uuid4()}"
    await seed(pool, redis, user_id)
    other_sessions = await seed(pool, redis, other)

    await api.delete("/sessions/memory", headers={"X-User-Id": user_id})

    assert await count_facts(pool, user_id) == 0
    assert await count_facts(pool, other) == 2, "one user's erasure is not another's"
    for sid in other_sessions:
        assert await redis.exists(si.history_key(sid)) == 1


# ------------------------------------------------------------------ failures


async def test_a_failed_deletion_does_not_report_success(api, pool, redis, user_id, mocker):
    """The one place in this feature where degrading quietly would be wrong.

    Everywhere else a failure costs personalisation. Here it would tell someone
    their data is gone when it is still there.
    """
    await seed(pool, redis, user_id)
    mocker.patch.object(
        FactsRepository,
        "delete_all_for_user",
        mocker.AsyncMock(side_effect=RuntimeError("postgres is on fire")),
    )

    response = await api.delete("/sessions/memory", headers={"X-User-Id": user_id})

    assert response.status_code == 500
    assert await count_facts(pool, user_id) == 2


async def test_deletion_without_a_database_is_an_error_not_a_shrug(api, redis, user_id, mocker):
    from app.core import database

    mocker.patch.object(database.db, "pool", None)

    response = await api.delete("/sessions/memory", headers={"X-User-Id": user_id})

    assert response.status_code == 503
