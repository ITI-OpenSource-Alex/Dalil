"""Tests for the session heartbeat endpoint and abandoned-session sweep.

Uses an in-memory FakeHeartbeatRepository injected via FastAPI dependency
overrides — no Postgres connection required.
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
    ) -> dict[str, Any]:
        session = {
            "id": session_id,
            "user_id": user_id,
            "status": status,
            "skill_area": skill_area,
            "exam_type": exam_type,
            "started_at": started_at or datetime.now(timezone.utc),
            "last_heartbeat_at": last_heartbeat_at,
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
        self, threshold_minutes: int = 10
    ) -> tuple[int, list[dict[str, Any]]]:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=threshold_minutes)

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
            elif s["started_at"] < threshold:
                stale = True

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
