"""Tests for the session heartbeat endpoint and abandoned-session sweep.

Two layers, and the split is deliberate.

Most tests use an in-memory FakeHeartbeatRepository injected via FastAPI
dependency overrides, which needs no Postgres and covers the endpoint contract.
That layer alone passed in full while the sweep could not write a single row:
the fake reimplements the sweep in Python and therefore has no CHECK constraint
to violate (BUG-053).

The two tests at the bottom go through the real repository against real
Postgres, and skip when no database is reachable. They are the ones that
actually pin the constraint and the threshold.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.heartbeat import get_heartbeat_repo, router as heartbeat_router
from app.services.sweep_service import sweep_abandoned_sessions


INTERNAL_KEY = "test-internal-key"


# ---------------------------------------------------------------------------
# In-memory fake repository
# ---------------------------------------------------------------------------

class FakeHeartbeatRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, dict[str, Any]] = {}

    def add_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        status: str = "in_progress",
        skill_area: str = "reading",
        exam_type: str = "academic",
        started_at: datetime | None = None,
        last_heartbeat_at: datetime | None = None,
        time_limit_seconds: int = 3600,
    ) -> dict[str, Any]:
        session = {
            "id": session_id,
            "user_id": user_id,
            "status": status,
            "skill_area": skill_area,
            "exam_type": exam_type,
            "started_at": started_at or datetime.now(timezone.utc),
            "last_heartbeat_at": last_heartbeat_at,
            # Reading is 3600s. The sweep now reads this instead of applying a
            # flat 10 minutes to every exam, so the fake has to carry it.
            "time_limit_seconds": time_limit_seconds,
        }
        self.sessions[session_id] = session
        return session

    async def get_session_for_heartbeat(
        self, session_id: UUID
    ) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        return {"user_id": session["user_id"], "status": session["status"]}

    async def touch_heartbeat(self, session_id: UUID) -> None:
        session = self.sessions.get(session_id)
        if session and session["status"] == "in_progress":
            session["last_heartbeat_at"] = datetime.now(timezone.utc)

    async def sweep_abandoned(
        self, grace_minutes: int = 10
    ) -> tuple[int, list[dict[str, Any]]]:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=grace_minutes)

        in_progress = [
            s for s in self.sessions.values() if s["status"] == "in_progress"
        ]
        checked = len(in_progress)

        abandoned: list[dict[str, Any]] = []
        for s in in_progress:
            hb = s.get("last_heartbeat_at")
            stale = False
            if hb is not None:
                stale = hb < threshold
            else:
                # Never heartbeated: allow the session's own time limit before
                # the grace window starts, so a client that does not heartbeat
                # still gets its full exam rather than 10 minutes of it.
                deadline = (
                    s["started_at"]
                    + timedelta(seconds=s.get("time_limit_seconds", 3600))
                    + timedelta(minutes=grace_minutes)
                )
                stale = deadline < now

            if stale:
                s["status"] = "abandoned"
                abandoned.append(
                    {
                        "id": s["id"],
                        "skill_area": s["skill_area"],
                        "exam_type": s["exam_type"],
                    }
                )

        return checked, abandoned


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_client(repo: FakeHeartbeatRepository) -> AsyncClient:
    app = FastAPI()
    app.include_router(heartbeat_router)
    app.dependency_overrides[get_heartbeat_repo] = lambda: repo
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _headers(user_id: UUID) -> dict[str, str]:
    return {
        "X-Internal-API-Key": INTERNAL_KEY,
        "X-User-Id": str(user_id),
    }


# ---------------------------------------------------------------------------
# Test 1: heartbeat updates last_heartbeat_at and returns 204
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_updates_timestamp_and_returns_204():
    repo = FakeHeartbeatRepository()
    user_id = uuid4()
    session_id = uuid4()
    repo.add_session(session_id=session_id, user_id=user_id)

    assert repo.sessions[session_id]["last_heartbeat_at"] is None

    async with _build_client(repo) as client:
        resp = await client.patch(
            f"/sessions/{session_id}/heartbeat",
            headers=_headers(user_id),
        )

    assert resp.status_code == 204
    assert repo.sessions[session_id]["last_heartbeat_at"] is not None


# ---------------------------------------------------------------------------
# Test 2: heartbeat returns 403 for wrong user, 404 for unknown session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_returns_403_for_wrong_user_and_404_for_unknown():
    repo = FakeHeartbeatRepository()
    owner_id = uuid4()
    intruder_id = uuid4()
    session_id = uuid4()
    repo.add_session(session_id=session_id, user_id=owner_id)

    async with _build_client(repo) as client:
        wrong_user = await client.patch(
            f"/sessions/{session_id}/heartbeat",
            headers=_headers(intruder_id),
        )
        unknown_session = await client.patch(
            f"/sessions/{uuid4()}/heartbeat",
            headers=_headers(owner_id),
        )

    assert wrong_user.status_code == 403
    assert unknown_session.status_code == 404


# ---------------------------------------------------------------------------
# Test 3: sweep marks stale session abandoned, leaves fresh one alone
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sweep_marks_stale_and_leaves_fresh():
    repo = FakeHeartbeatRepository()
    now = datetime.now(timezone.utc)

    stale_id = uuid4()
    repo.add_session(
        session_id=stale_id,
        user_id=uuid4(),
        started_at=now - timedelta(minutes=20),
        last_heartbeat_at=now - timedelta(minutes=15),
    )

    fresh_id = uuid4()
    repo.add_session(
        session_id=fresh_id,
        user_id=uuid4(),
        started_at=now - timedelta(minutes=5),
        last_heartbeat_at=now - timedelta(minutes=1),
    )

    checked, abandoned_count = await sweep_abandoned_sessions(repo)

    assert checked == 2
    assert abandoned_count == 1
    assert repo.sessions[stale_id]["status"] == "abandoned"
    assert repo.sessions[fresh_id]["status"] == "in_progress"


# ---------------------------------------------------------------------------
# Test 4: integration — heartbeat keeps session alive, clock advance triggers
#          sweep abandonment and prometheus metric increment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_heartbeat_then_sweep_with_clock_advance():
    from app.core.metrics import goa_exam_sessions_total

    repo = FakeHeartbeatRepository()
    user_id = uuid4()
    session_id = uuid4()
    repo.add_session(
        session_id=session_id,
        user_id=user_id,
        skill_area="listening",
        exam_type="academic",
    )

    # Step 1: send heartbeat → session stays alive
    async with _build_client(repo) as client:
        resp = await client.patch(
            f"/sessions/{session_id}/heartbeat",
            headers=_headers(user_id),
        )
    assert resp.status_code == 204
    assert repo.sessions[session_id]["last_heartbeat_at"] is not None

    # Step 2: run sweep immediately → session is fresh, nothing abandoned
    checked, abandoned_count = await sweep_abandoned_sessions(repo)
    assert repo.sessions[session_id]["status"] == "in_progress"
    assert abandoned_count == 0

    # Step 3: simulate 11 minutes passing by rewinding the heartbeat timestamp
    repo.sessions[session_id]["last_heartbeat_at"] = datetime.now(
        timezone.utc
    ) - timedelta(minutes=11)

    # Capture metric before sweep
    before = (
        goa_exam_sessions_total.labels(
            skill_area="listening",
            exam_type="academic",
            outcome="abandoned",
        )
        ._value.get()
    )

    # Step 4: run sweep → session is now abandoned
    checked, abandoned_count = await sweep_abandoned_sessions(repo)
    assert repo.sessions[session_id]["status"] == "abandoned"
    assert abandoned_count == 1

    # Step 5: verify prometheus metric incremented
    after = (
        goa_exam_sessions_total.labels(
            skill_area="listening",
            exam_type="academic",
            outcome="abandoned",
        )
        ._value.get()
    )
    assert after == before + 1


# ---------------------------------------------------------------------------
# Real-Postgres tests.
#
# Everything above this line runs against FakeHeartbeatRepository, which
# reimplements the sweep in Python. That is why 262 lines of passing tests sat
# on top of a sweep that could not write a single row: migration 006 added
# last_heartbeat_at but never extended the status CHECK constraint, so
# `SET status = 'abandoned'` raised CheckViolationError on every run, was caught
# by run_sweep_loop's `except Exception`, logged as sweep_error and retried
# every 300 seconds forever (BUG-053). A fake cannot have a CHECK constraint.
#
# These two go through the real repository against real Postgres. They are the
# tests that would have caught BUG-053 and BUG-054 respectively.
# ---------------------------------------------------------------------------


async def _private_pool():
    """A pool owned by the calling test.

    The global `db` pool is created once and bound to whichever event loop first
    touched it. pytest-asyncio gives each test its own loop, so sharing it makes
    the second test fail with asyncpg InterfaceError -- passing alone, failing in
    a suite, which reads like flakiness rather than the setup problem it is.
    """
    import asyncpg
    from app.core.config import settings
    from app.repositories.heartbeat_repository import HeartbeatRepository  # noqa: F401

    try:
        return await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=2)
    except Exception:
        pytest.skip("Database not available for integration test")


async def _seed_session(conn, *, session_id, user_id, started_at, time_limit_seconds,
                        last_heartbeat_at=None, skill_area="reading"):
    question_id = uuid4()
    # questions has a unique (book_ref, test_number, skill_area). A fixed
    # book_ref would collide between these two tests and, worse, leave a row
    # behind whenever seeding failed part-way, so the next run failed for a
    # reason that had nothing to do with the code under test.
    book_ref = f"hb_test_{question_id.hex[:12]}"
    await conn.execute(
        """
        INSERT INTO questions (id, book_ref, test_number, exam_type, skill_area,
                               passage_text, audio_s3_key, answer_key, questions)
        VALUES ($1, $2, 1, 'academic', $3, '', '', '{}', '[]')
        """,
        question_id,
        book_ref,
        skill_area,
    )
    await conn.execute(
        """
        INSERT INTO exam_sessions (id, user_id, question_id, exam_type, skill_area,
                                   status, started_at, time_limit_seconds,
                                   last_heartbeat_at)
        VALUES ($1, $2, $3, 'academic', $4, 'in_progress', $5, $6, $7)
        """,
        session_id, user_id, question_id, skill_area,
        started_at, time_limit_seconds, last_heartbeat_at,
    )
    return question_id


@pytest.mark.asyncio
async def test_real_sweep_can_write_abandoned_status():
    """BUG-053: the CHECK constraint must permit 'abandoned'.

    Before migration 007 this raised
    asyncpg.exceptions.CheckViolationError and the sweep silently no-opped.
    """
    from app.repositories.heartbeat_repository import HeartbeatRepository

    pool = await _private_pool()

    session_id, user_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        question_id = await _seed_session(
            conn, session_id=session_id, user_id=user_id,
            started_at=now - timedelta(minutes=90),
            time_limit_seconds=3600,
            last_heartbeat_at=now - timedelta(minutes=30),
        )

    try:
        _, abandoned = await HeartbeatRepository(pool).sweep_abandoned()
        assert any(r["id"] == session_id for r in abandoned), (
            "the sweep did not abandon a session that has been silent for 30 "
            "minutes -- if this raises CheckViolationError instead, migration "
            "007 is missing"
        )
        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT status FROM exam_sessions WHERE id = $1", session_id
            )
        assert status == "abandoned"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM exam_sessions WHERE id = $1", session_id)
            await conn.execute("DELETE FROM questions WHERE id = $1", question_id)
        await pool.close()


@pytest.mark.asyncio
async def test_real_sweep_spares_a_60_minute_exam_that_never_heartbeats():
    """BUG-054: a candidate must not lose an exam to a client that stays quiet.

    The original sweep abandoned any session started more than 10 minutes ago
    when last_heartbeat_at was NULL. Reading is 60 minutes and no client sent
    heartbeats, so with the constraint fixed every candidate would have been
    abandoned at minute 10 and met a 403 on submit.
    """
    from app.repositories.heartbeat_repository import HeartbeatRepository

    pool = await _private_pool()

    session_id, user_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        question_id = await _seed_session(
            conn, session_id=session_id, user_id=user_id,
            # 20 minutes into a 60-minute exam, never heartbeated. Well past the
            # old flat 10-minute threshold.
            started_at=now - timedelta(minutes=20),
            time_limit_seconds=3600,
            last_heartbeat_at=None,
        )

    try:
        _, abandoned = await HeartbeatRepository(pool).sweep_abandoned()
        assert not any(r["id"] == session_id for r in abandoned), (
            "a candidate 20 minutes into a 60-minute exam was marked abandoned; "
            "the sweep is using a flat threshold instead of the session's own "
            "time_limit_seconds"
        )
        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT status FROM exam_sessions WHERE id = $1", session_id
            )
        assert status == "in_progress"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM exam_sessions WHERE id = $1", session_id)
            await conn.execute("DELETE FROM questions WHERE id = $1", question_id)
        await pool.close()
