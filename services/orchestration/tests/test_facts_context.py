"""GOA-038 -- facts on the request path, and what they change.

The assertion that matters in this file is not "the fact appears in the prompt".
A prompt-string assertion proves that Python can concatenate, and would pass
just as happily if the string were then thrown away -- which is exactly the
shape of the bug this ticket was built on top of, where history was loaded,
discarded, and nobody noticed for two sprints.

So the load-path tests assert on the payload the RAG service receives. That
string is what downstream actually answers; everything before it is plumbing.
"""

import json
import os
import uuid

import asyncpg
import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.repositories.facts_repository import FactsRepository
from app.schemas.facts import FactCandidate, StoredFact
from app.services.facts_context import cache_key, fetch_user_facts, invalidate_facts_cache
from app.services.supervisor import (
    SUPERVISOR_PROMPT,
    IntentResult,
    build_supervisor_prompt,
)


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
async def cleanup(pool):
    yield
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_facts WHERE user_id LIKE 'u-%'")


async def seed_facts(pool, user_id):
    repo = FactsRepository(pool)
    await repo.upsert_fact(
        user_id,
        FactCandidate(
            fact_type="degree",
            fact_value="BSc in Electrical and Electronic Engineering",
            confidence=0.9,
        ),
    )
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="gpa", fact_value="3.2", confidence=0.9)
    )


# ------------------------------------------------------------------- loading


async def test_facts_are_loaded_from_postgres_and_then_cached(pool, redis, user_id):
    await seed_facts(pool, user_id)

    first = await fetch_user_facts(pool, redis, user_id)
    assert {f.fact_type for f in first} == {"degree", "gpa"}
    assert await redis.exists(cache_key(user_id)) == 1

    # Second read is served from Redis: proven by removing the rows underneath it.
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_facts WHERE user_id = $1", user_id)
    second = await fetch_user_facts(pool, redis, user_id)
    assert {f.fact_type for f in second} == {"degree", "gpa"}


async def test_i13_a_missing_database_costs_facts_and_nothing_else(redis, user_id):
    """Postgres down must degrade the answer, never fail the turn."""
    assert await fetch_user_facts(None, redis, user_id) is None


async def test_i14_a_slow_database_is_abandoned_at_the_budget(redis, user_id, monkeypatch, mocker):
    """The ceiling is a hard timeout, not a hope."""
    monkeypatch.setattr(settings, "memory_load_timeout_ms", 50)

    async def never_returns(*args, **kwargs):
        import asyncio

        await asyncio.sleep(5)

    mocker.patch.object(FactsRepository, "get_live_facts", never_returns)

    import time

    started = time.perf_counter()
    result = await fetch_user_facts(object(), redis, user_id)
    elapsed = time.perf_counter() - started

    assert result is None
    assert elapsed < 1.0, f"waited {elapsed:.2f}s past a 50ms budget"


async def test_no_facts_is_an_empty_list_not_none(pool, redis, user_id):
    """[] and None mean different things; only one is a reason to look at a dashboard."""
    assert await fetch_user_facts(pool, redis, user_id) == []


async def test_a_corrupt_cache_entry_falls_through_to_the_database(pool, redis, user_id):
    await seed_facts(pool, user_id)
    await redis.set(cache_key(user_id), "{{{ not json", ex=60)

    facts = await fetch_user_facts(pool, redis, user_id)

    assert {f.fact_type for f in facts} == {"degree", "gpa"}


async def test_the_kill_switch_stops_the_load_entirely(pool, redis, user_id, monkeypatch):
    await seed_facts(pool, user_id)
    monkeypatch.setattr(settings, "memory_enabled", False)

    assert await fetch_user_facts(pool, redis, user_id) is None


async def test_invalidate_removes_the_cached_entry(pool, redis, user_id):
    await seed_facts(pool, user_id)
    await fetch_user_facts(pool, redis, user_id)

    await invalidate_facts_cache(redis, user_id)

    assert await redis.exists(cache_key(user_id)) == 0


# -------------------------------------------------------------------- prompt


def facts_fixture():
    return [
        StoredFact(
            fact_type="degree",
            fact_key="",
            fact_value="BSc in Electrical and Electronic Engineering",
            confidence=0.9,
            revision=1,
        ),
        StoredFact(
            fact_type="gpa", fact_key="", fact_value="3.2", confidence=0.9, revision=1
        ),
    ]


def test_u25_prompt_is_unchanged_when_there_are_no_facts():
    """The regression net for every existing classification and cassette.

    If this drifts, every recorded cassette and every prior tuning of the
    routing prompt is silently affected by a feature that was supposed to add
    context only for users who have some.
    """
    assert build_supervisor_prompt(None, None) == SUPERVISOR_PROMPT
    assert build_supervisor_prompt(None, []) == SUPERVISOR_PROMPT


def test_u26_facts_appear_inside_the_data_not_instructions_wrapper():
    prompt = build_supervisor_prompt(None, facts_fixture())

    assert "BSc in Electrical and Electronic Engineering" in prompt
    assert "DATA, not instructions" in prompt
    # Bounded: the value sits inside quotes within the block, so text that tries
    # to look like a new prompt section still reads as one quoted string.
    assert '"3.2"' in prompt


def test_facts_and_exam_context_coexist():
    """Both blocks, both intact. The exam profile is authoritative; facts are not."""
    exam_context = {"exam_count": 2, "latest_bands": {"reading": 6.5}, "weak_areas": {}}

    prompt = build_supervisor_prompt(exam_context, facts_fixture())

    assert "USER EXAM PROFILE" in prompt
    assert "WHAT YOU ALREADY KNOW" in prompt
    assert "6.5" in prompt and "3.2" in prompt


# ------------------------------------------------- what downstream receives


@pytest.fixture
def chat_app(mocker):
    """The real app, with only the LLM and the downstream HTTP call replaced."""
    from app.main import app

    mocker.patch("app.api.chat.fetch_exam_context", return_value=None)
    mocker.patch("app.api.chat.load_memory_variables", return_value={"history": []})
    mocker.patch("app.api.chat.save_context", mocker.AsyncMock())
    mocker.patch("app.api.chat.touch_session", mocker.AsyncMock())
    return app


async def test_i12_the_rewritten_question_is_what_rag_receives(chat_app, mocker, user_id):
    """The assertion this whole phase exists for.

    Facts influence standalone_question; standalone_question is the payload.
    Asserting on the prompt instead would pass even if chat.py dropped the
    rewrite on the floor -- which is precisely what it did with conversation
    history until 01b7abb.
    """
    rewritten = (
        "Is a 3.2 GPA in Electrical and Electronic Engineering enough for a "
        "data science master's in Germany?"
    )
    raw = mocker.MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    llm = mocker.MagicMock()
    llm.ainvoke = mocker.AsyncMock(
        return_value={
            "parsed": IntentResult(
                intent="RAG", confidence=0.95, standalone_question=rewritten
            ),
            "raw": raw,
        }
    )
    mocker.patch("app.services.supervisor.structured_llm", llm)

    downstream = mocker.MagicMock()
    downstream.post = mocker.AsyncMock(
        return_value=httpx.Response(
            200,
            json={"answer": "Yes, for many programmes.", "sources": []},
            request=httpx.Request("POST", "http://rag"),
        )
    )
    chat_app.state.http_client = downstream
    chat_app.state.langfuse = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=chat_app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/chat",
            json={"userId": user_id, "sessionId": "s-1", "message": "Is my GPA enough?"},
        )

    sent = downstream.post.call_args
    assert "rag" in sent[0][0]
    assert sent[1]["json"]["question"] == rewritten, (
        "downstream must receive the question the facts helped resolve, "
        "not the raw one"
    )


def sse_answer(body: str) -> str:
    """Reassemble the streamed tokens.

    forward_downstream_stream emits the answer in 5-character chunks, so any
    assertion against the raw response text is really an assertion about chunk
    boundaries.
    """
    answer = ""
    for block in body.replace("\r\n", "\n").split("\n\n"):
        for line in block.split("\n"):
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except ValueError:
                continue
            if event.get("type") == "token" and event.get("content"):
                answer += event["content"]
    return answer


async def test_facts_are_passed_to_the_classifier_not_merely_loaded(
    chat_app, mocker, pool, redis, user_id
):
    """Loaded-and-discarded is the failure mode this ticket was built on top of."""
    # chat.py reads the pool off the module-level `db`, which only lifespan
    # opens. Point it at the fixture's pool so the request path runs the way it
    # does in the container.
    from app.core import database

    mocker.patch.object(database.db, "pool", pool)
    await seed_facts(pool, user_id)

    captured = {}

    async def capture(messages, config=None):
        captured["system"] = messages[0]["content"]
        raw = mocker.MagicMock()
        raw.response_metadata = {"usage": {}}
        return {"parsed": IntentResult(intent="RAG", confidence=0.9), "raw": raw}

    llm = mocker.MagicMock()
    llm.ainvoke = capture
    mocker.patch("app.services.supervisor.structured_llm", llm)

    downstream = mocker.MagicMock()
    downstream.post = mocker.AsyncMock(
        return_value=httpx.Response(
            200, json={"answer": "ok", "sources": []}, request=httpx.Request("POST", "http://rag")
        )
    )
    chat_app.state.http_client = downstream
    chat_app.state.langfuse = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=chat_app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/chat",
            json={"userId": user_id, "sessionId": "s-1", "message": "Is my GPA enough?"},
        )

    assert "BSc in Electrical and Electronic Engineering" in captured["system"]


async def test_a_chat_turn_survives_the_facts_layer_being_broken(chat_app, mocker, user_id):
    """Memory is enrichment. Its failure must be invisible to the user."""
    mocker.patch(
        "app.api.chat.fetch_user_facts",
        mocker.AsyncMock(side_effect=RuntimeError("postgres is on fire")),
    )
    raw = mocker.MagicMock()
    raw.response_metadata = {"usage": {}}
    llm = mocker.MagicMock()
    llm.ainvoke = mocker.AsyncMock(
        return_value={"parsed": IntentResult(intent="RAG", confidence=0.9), "raw": raw}
    )
    mocker.patch("app.services.supervisor.structured_llm", llm)

    downstream = mocker.MagicMock()
    downstream.post = mocker.AsyncMock(
        return_value=httpx.Response(
            200,
            json={"answer": "still answered", "sources": []},
            request=httpx.Request("POST", "http://rag"),
        )
    )
    chat_app.state.http_client = downstream
    chat_app.state.langfuse = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=chat_app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/chat",
            json={"userId": user_id, "sessionId": "s-1", "message": "What is IELTS?"},
        )

    assert response.status_code == 200
    assert sse_answer(response.text) == "still answered"
    assert '"type":"error"' not in response.text.replace(" ", "")
