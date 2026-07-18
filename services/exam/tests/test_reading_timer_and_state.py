from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from app.services.session_service import SessionService


class FakeSessionRepository:
    def __init__(self, session: dict[str, Any]) -> None:
        self._session = session

    async def get_by_id(self, session_id: Any) -> dict[str, Any] | None:
        return self._session

    async def create(self, **kwargs: Any) -> None:
        pass

    async def submit(self, session_id: Any) -> None:
        self._session["status"] = "submitted"

    async def mark_scored(self, session_id: Any) -> None:
        self._session["status"] = "scored"


class FakeQuestionRepository:
    def __init__(self, question: dict[str, Any]) -> None:
        self._question = question

    async def get_by_id(self, question_id: Any) -> dict[str, Any] | None:
        return self._question

    async def get_random_unseen_question(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._question


class FakeResultRepository:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> None:
        self.saved = kwargs

    async def get_by_session(self, session_id: Any) -> dict[str, Any] | None:
        if self.saved and self.saved.get("session_id") == session_id:
            return self.saved
        return None


def _make_session(
    elapsed_seconds: float = 100.0,
    status: str = "in_progress",
) -> dict[str, Any]:
    started = datetime.now(timezone.utc) - timedelta(seconds=elapsed_seconds)
    return {
        "id": uuid4(),
        "user_id": uuid4(),
        "question_id": uuid4(),
        "exam_type": "academic",
        "skill_area": "reading",
        "status": status,
        "started_at": started,
        "submitted_at": None,
        "time_limit_seconds": 3600,
    }


def _make_question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "test-book",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "reading",
        "passage_text": "Passage 1\n---\nPassage 2\n---\nPassage 3",
        "audio_s3_key": None,
        "questions": [{"id": str(i), "prompt": f"Q{i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }


@pytest.mark.asyncio
async def test_expired_session_returns_403() -> None:
    session = _make_session(elapsed_seconds=3631)
    question = _make_question()
    service = SessionService(
        session_repository=FakeSessionRepository(session),
        question_repository=FakeQuestionRepository(question),
        result_repository=FakeResultRepository(),
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_reading_session(
            session_id=session["id"],
            answers={"1": "A1"},
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_double_submit_returns_409() -> None:
    session = _make_session(status="scored")
    question = _make_question()
    result_repo = FakeResultRepository()
    result_repo.saved = {
        "session_id": session["id"],
        "raw_score": 10,
        "band_score": 4.0,
    }
    service = SessionService(
        session_repository=FakeSessionRepository(session),
        question_repository=FakeQuestionRepository(question),
        result_repository=result_repo,
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_reading_session(
            session_id=session["id"],
            answers={"1": "A1"},
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_valid_submit_succeeds() -> None:
    session = _make_session(elapsed_seconds=100)
    question = _make_question()
    result_repo = FakeResultRepository()
    service = SessionService(
        session_repository=FakeSessionRepository(session),
        question_repository=FakeQuestionRepository(question),
        result_repository=result_repo,
    )

    result = await service.submit_reading_session(
        session_id=session["id"],
        answers={str(i): f"A{i}" for i in range(1, 41)},
    )

    assert result["raw_score"] == 40
    assert result["band_score"] == 9.0
    assert result_repo.saved is not None
