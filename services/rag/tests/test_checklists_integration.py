"""
GOA-084 -- integration tests for checklist persistence.

Like test_visa_integration.py, these require a REAL, live Postgres connection: real
schema, real unique-index/ON CONFLICT race behavior, real get-or-create persistence.
Only the external Anthropic LLM call is mocked (no real API keys are configured for
this project, matching test_query.py / test_visa_integration.py).

Run with the docker-compose postgres service up:

    docker compose up -d postgres redis-cache
    DATABASE_URL=postgresql://goa:goa_pass@localhost:5432/rag_db \
    pytest services/rag/tests/test_checklists_integration.py -v

Each test creates its own fixture rows (scoped by a fresh random user_id) and cleans
up afterward, leaving the database in the state it found it.
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.checklists import GeneratedChecklist, GeneratedChecklistItem

# Seeded by 008_update_program_requirements.sql -- always present once migrations
# have run, so these tests don't need to insert their own program_requirements row.
SEED_PROGRAM_ID = "11111111-1111-1111-1111-111111111111"

# Only the ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS portion of
# 027_checklist_persistence.sql. The migration's DELETE statements are meant to run
# exactly once, on the placeholder-era rows, and are already guaranteed to run only
# once by migrations_log (app/core/database.py); re-executing them here would wipe
# real checklist rows this same test file creates. This checks the part that
# genuinely can be re-applied safely.
_SCHEMA_ONLY_SQL = """
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS items JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS generated_by VARCHAR(20) NOT NULL DEFAULT 'llm';
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();
CREATE UNIQUE INDEX IF NOT EXISTS uq_checklists_user_program
    ON checklists (user_id, program_id);
ALTER TABLE checklist_item_states ADD COLUMN IF NOT EXISTS is_checked BOOLEAN NOT NULL DEFAULT FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_checklist_item_states_checklist_item
    ON checklist_item_states (checklist_id, item_key);
"""


@pytest.fixture
def live_client():
    """A TestClient used as a context manager triggers the app's real lifespan
    startup (db.connect() / db.disconnect()), giving request handlers a real,
    connected app.core.database.db.pool -- matches test_visa_integration.py."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """Mock only the external Anthropic call; checklist generation still runs its
    real prompt-building, normalization, and persistence path against the live DB."""
    parsed = GeneratedChecklist(
        items=[
            GeneratedChecklistItem(item_id="valid_passport", title="Valid passport"),
            GeneratedChecklistItem(item_id="ielts_retake", title="Retake IELTS"),
        ]
    )
    mock_raw = MagicMock(response_metadata={"usage": {"input_tokens": 10, "output_tokens": 5}})
    structured_llm = MagicMock()
    structured_llm.ainvoke = AsyncMock(return_value={"parsed": parsed, "raw": mock_raw})
    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output = MagicMock(return_value=structured_llm)
    monkeypatch.setattr(
        "app.services.checklist_generator.ChatAnthropic",
        MagicMock(return_value=mock_llm_instance),
    )
    return structured_llm.ainvoke


def _run(coro):
    """Runs a one-off coroutine against a fresh connection/event loop, independent of
    whatever event loop TestClient uses internally for the app's own db.pool --
    mirrors test_visa_integration.py's helper of the same name."""
    return asyncio.run(coro)


async def _connect():
    return await asyncpg.connect(dsn=settings.database_url)


async def _cleanup_user(user_id, program_id=SEED_PROGRAM_ID):
    conn = await _connect()
    try:
        await conn.execute(
            "DELETE FROM checklists WHERE user_id = $1 AND program_id = $2",
            user_id,
            program_id,
        )
    finally:
        await conn.close()


async def _fetch_checklists(user_id, program_id=SEED_PROGRAM_ID):
    conn = await _connect()
    try:
        return await conn.fetch(
            "SELECT id, items, generated_by FROM checklists WHERE user_id = $1 AND program_id = $2",
            user_id,
            program_id,
        )
    finally:
        await conn.close()


async def _fetch_item_states(checklist_id):
    conn = await _connect()
    try:
        return await conn.fetch(
            "SELECT item_key, is_checked FROM checklist_item_states WHERE checklist_id = $1",
            checklist_id,
        )
    finally:
        await conn.close()


def new_user_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Schema: the unique indexes the get-or-create race and item-state upsert rely on
# ---------------------------------------------------------------------------


def test_migration_027_schema_changes_are_idempotent():
    async def _apply_twice():
        conn = await _connect()
        try:
            await conn.execute(_SCHEMA_ONLY_SQL)
            await conn.execute(_SCHEMA_ONLY_SQL)
            return await conn.fetch(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename IN ('checklists', 'checklist_item_states')"
            )
        finally:
            await conn.close()

    indexes = {row["indexname"] for row in _run(_apply_twice())}
    assert "uq_checklists_user_program" in indexes
    assert "uq_checklist_item_states_checklist_item" in indexes


# ---------------------------------------------------------------------------
# GET /checklists/{programId} -- get-or-create against the real database
# ---------------------------------------------------------------------------


def test_get_checklist_persists_and_is_reused_across_requests(live_client, mock_llm):
    user_id = new_user_id()
    try:
        first = live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_id})
        second = live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_id})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["checklistId"] == second.json()["checklistId"]
        assert mock_llm.call_count == 1  # the second GET must not regenerate

        rows = _run(_fetch_checklists(user_id))
        assert len(rows) == 1
    finally:
        _run(_cleanup_user(user_id))


def test_get_checklist_unknown_program_returns_404(live_client):
    response = live_client.get(f"/checklists/{uuid.uuid4()}", headers={"X-User-ID": new_user_id()})
    assert response.status_code == 404


def test_different_users_get_independent_checklists(live_client, mock_llm):
    user_a, user_b = new_user_id(), new_user_id()
    try:
        resp_a = live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_a})
        resp_b = live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_b})
        assert resp_a.json()["checklistId"] != resp_b.json()["checklistId"]

        put_resp = live_client.put(
            f"/checklists/{SEED_PROGRAM_ID}/items/valid_passport",
            json={"checked": True},
            headers={"X-User-ID": user_a},
        )
        assert put_resp.status_code == 200

        resp_b_after = live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_b})
        assert all(not item["checked"] for item in resp_b_after.json()["items"])
    finally:
        _run(_cleanup_user(user_a))
        _run(_cleanup_user(user_b))


# ---------------------------------------------------------------------------
# PUT /checklists/{programId}/items/{itemId}
# ---------------------------------------------------------------------------


def test_put_toggles_checked_state_and_persists(live_client, mock_llm):
    user_id = new_user_id()
    try:
        live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_id})

        checked_resp = live_client.put(
            f"/checklists/{SEED_PROGRAM_ID}/items/valid_passport",
            json={"checked": True},
            headers={"X-User-ID": user_id},
        )
        assert checked_resp.status_code == 200
        assert checked_resp.json()["checked"] is True

        get_resp = live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_id})
        items = {item["itemId"]: item["checked"] for item in get_resp.json()["items"]}
        assert items["valid_passport"] is True
        assert items["ielts_retake"] is False

        unchecked_resp = live_client.put(
            f"/checklists/{SEED_PROGRAM_ID}/items/valid_passport",
            json={"checked": False},
            headers={"X-User-ID": user_id},
        )
        assert unchecked_resp.json()["checked"] is False
    finally:
        _run(_cleanup_user(user_id))


def test_put_unknown_item_returns_404(live_client, mock_llm):
    user_id = new_user_id()
    try:
        live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_id})
        response = live_client.put(
            f"/checklists/{SEED_PROGRAM_ID}/items/not_a_real_item",
            json={"checked": True},
            headers={"X-User-ID": user_id},
        )
        assert response.status_code == 404
    finally:
        _run(_cleanup_user(user_id))


def test_put_without_existing_checklist_returns_404(live_client):
    response = live_client.put(
        f"/checklists/{SEED_PROGRAM_ID}/items/valid_passport",
        json={"checked": True},
        headers={"X-User-ID": new_user_id()},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Concurrency: the get-or-create race at the database level
# ---------------------------------------------------------------------------


def test_concurrent_checklist_creation_yields_exactly_one_row():
    """Races five independent connections through the exact
    INSERT ... ON CONFLICT DO NOTHING statement checklist_repo.create_checklist
    uses. Uses standalone connections rather than app.core.database.db's own pool
    to avoid binding an asyncpg connection to the wrong event loop (see
    test_visa_integration.py's _run/_connect) -- this verifies
    uq_checklists_user_program (migration 027) is what prevents a duplicate
    checklist under concurrent get-or-create, independent of any Python-level
    locking in the service layer."""
    user_id = new_user_id()

    async def _insert_once():
        conn = await _connect()
        try:
            return await conn.fetchrow(
                """
                INSERT INTO checklists (program_id, user_id, title, items, generated_by)
                VALUES ($1, $2, 'Race test', '[]'::jsonb, 'llm')
                ON CONFLICT (user_id, program_id) DO NOTHING
                RETURNING id
                """,
                SEED_PROGRAM_ID,
                user_id,
            )
        finally:
            await conn.close()

    async def _race():
        return await asyncio.gather(*[_insert_once() for _ in range(5)])

    try:
        results = _run(_race())
        winners = [r for r in results if r is not None]
        assert len(winners) == 1

        rows = _run(_fetch_checklists(user_id))
        assert len(rows) == 1
    finally:
        _run(_cleanup_user(user_id))


# ---------------------------------------------------------------------------
# checklist_item_states cascades when its checklist is deleted (FK declared in
# 006_add_checklists.sql: ON DELETE CASCADE)
# ---------------------------------------------------------------------------


def test_deleting_checklist_cascades_item_states(live_client, mock_llm):
    user_id = new_user_id()
    try:
        live_client.get(f"/checklists/{SEED_PROGRAM_ID}", headers={"X-User-ID": user_id})
        live_client.put(
            f"/checklists/{SEED_PROGRAM_ID}/items/valid_passport",
            json={"checked": True},
            headers={"X-User-ID": user_id},
        )
        rows = _run(_fetch_checklists(user_id))
        checklist_id = rows[0]["id"]
        assert len(_run(_fetch_item_states(checklist_id))) == 1

        _run(_cleanup_user(user_id))

        assert len(_run(_fetch_item_states(checklist_id))) == 0
    finally:
        _run(_cleanup_user(user_id))


# ---------------------------------------------------------------------------
# GOA-035: GET /checklists/{program_id}/financial against the live program_requirements
# row (SEED_PROGRAM_ID -> Germany, seeded by 008_update_program_requirements.sql).
# get_student_visa_finance itself is GOA-108's territory and already covered by
# test_visa_task6.py; this only pins that the checklist route looks up the real
# program's country and hands back visa_finance's output unchanged.
# ---------------------------------------------------------------------------


def test_get_financial_requirements_uses_real_program_country(live_client, monkeypatch):
    finance_items = [
        {
            "type": "informational",
            "country": "Germany",
            "issuing_body": "Fintiba",
            "message": "requires proof of 11904 EUR per year via blocked_account",
            "source_url": "https://www.fintiba.com/blocked-account/",
            "last_verified_at": None,
        }
    ]
    monkeypatch.setattr(
        "app.services.checklist_financial.get_student_visa_finance",
        AsyncMock(return_value=finance_items),
    )

    response = live_client.get(
        f"/checklists/{SEED_PROGRAM_ID}/financial", headers={"X-User-ID": new_user_id()}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["programId"] == SEED_PROGRAM_ID
    assert body["items"] == [
        {
            "type": "informational",
            "country": "Germany",
            "issuingBody": "Fintiba",
            "message": "requires proof of 11904 EUR per year via blocked_account",
            "sourceUrl": "https://www.fintiba.com/blocked-account/",
            "lastVerifiedAt": None,
        }
    ]


def test_get_financial_requirements_empty_when_no_visa_data(live_client, monkeypatch):
    monkeypatch.setattr(
        "app.services.checklist_financial.get_student_visa_finance",
        AsyncMock(return_value=[]),
    )

    response = live_client.get(
        f"/checklists/{SEED_PROGRAM_ID}/financial", headers={"X-User-ID": new_user_id()}
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
