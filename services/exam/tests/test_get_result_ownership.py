"""Owner check on GET /sessions/{id}/result."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.services.session_service import SessionService


def _build_service(
    *,
    owner_id: UUID,
    session_id: UUID,
) -> SessionService:
    question_id = uuid4()

    class FakeSessions:
        async def get_by_id(self, sid: UUID) -> dict:
            return {
                "id": session_id,
                "user_id": owner_id,
                "status": "scored",
                "skill_area": "speaking",
                "question_id": question_id,
            }

    class FakeResults:
        async def get_by_session(self, sid: UUID) -> dict:
            return {
                "id": uuid4(),
                "session_id": session_id,
                "user_id": owner_id,
                "skill_area": "speaking",
                "raw_score": None,
                "band_score": 6.5,
                "section_scores": "{}",
                "graded_at": datetime.now(timezone.utc),
            }

    class FakeQuestions:
        async def get_by_id(self, qid: UUID) -> dict:
            return {"id": qid, "answer_key": "{}"}

    return SessionService(
        session_repository=FakeSessions(),
        question_repository=FakeQuestions(),
        result_repository=FakeResults(),
        writing_response_repository=None,
        writing_client=None,
    )


@pytest.mark.asyncio
async def test_get_result_rejects_non_owner() -> None:
    owner_id = uuid4()
    other_id = uuid4()
    session_id = uuid4()
    svc = _build_service(owner_id=owner_id, session_id=session_id)

    with pytest.raises(HTTPException) as exc:
        await svc.get_result(session_id, requester_id=other_id)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Session belongs to another user"


@pytest.mark.asyncio
async def test_get_result_allows_owner() -> None:
    owner_id = uuid4()
    session_id = uuid4()
    svc = _build_service(owner_id=owner_id, session_id=session_id)

    result = await svc.get_result(session_id, requester_id=owner_id)

    assert result["band_score"] == 6.5
    assert result["session_id"] == session_id
    assert result["user_id"] == owner_id
