import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

# Ensure exam service settings are available for import
os.environ.setdefault("DATABASE_URL", "postgresql://goa:goa_pass@localhost:5432/exam_test")
os.environ.setdefault("INTERNAL_API_KEY", "supersecret_internal_key_123")
os.environ.setdefault("SPEAKING_SERVICE_URL", "http://test-speaking")
os.environ.setdefault("WRITING_SERVICE_URL", "http://test-writing")

ROOT = Path(__file__).resolve().parents[2] / "services" / "exam"
sys.path.insert(0, str(ROOT))

from app.api.internal import router as internal_router
from app.api.reading import get_session_service as reading_get_session_service
from app.api.reading import router as reading_router
from app.services.session_service import SessionService, TimerService


def _correct_reading_answers() -> dict[str, str]:
    return {str(i): f"A{i}" for i in range(1, 41)}


class FakeReadingSessionService:
    def __init__(self) -> None:
        self.session_id = uuid4()

    async def create_reading_session(self, user_id: Any, exam_type: str) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "passages": ["Passage 1", "Passage 2", "Passage 3"],
            "questions": [{"id": str(i), "prompt": f"Q{i}"} for i in range(1, 41)],
            "time_limit_seconds": 3600,
        }

    async def submit_reading_session(self, session_id: Any, answers: dict[str, str]) -> dict[str, Any]:
        assert str(session_id) == str(self.session_id)
        return {
            "raw_score": 40,
            "band_score": 9.0,
            "per_question_result": {},
            "section_breakdown": {},
        }


class FakeSessionRepository:
    def __init__(self, session: dict[str, Any]) -> None:
        self.session = session

    async def get_by_id(self, session_id: Any) -> dict[str, Any] | None:
        return self.session

    async def create(self, **kwargs: Any) -> None:
        pass

    async def submit(self, session_id: Any) -> None:
        self.session["status"] = "submitted"

    async def mark_scored(self, session_id: Any) -> None:
        self.session["status"] = "scored"


class FakeQuestionRepository:
    def __init__(self, question: dict[str, Any]) -> None:
        self.question = question

    async def get_by_id(self, question_id: Any) -> dict[str, Any] | None:
        return self.question

    async def get_random_unseen_question(self, **kwargs: Any) -> dict[str, Any] | None:
        return self.question


class FakeResultRepository:
    async def create(self, **kwargs: Any) -> None:
        pass

    async def get_by_session(self, session_id: Any) -> dict[str, Any] | None:
        return None


def _build_expired_reading_session() -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    started = datetime.now(timezone.utc) - timedelta(seconds=3600 + 60)
    return {
        "id": uuid4(),
        "user_id": uuid4(),
        "question_id": uuid4(),
        "exam_type": "academic",
        "skill_area": "reading",
        "status": "in_progress",
        "started_at": started,
        "submitted_at": None,
        "time_limit_seconds": 3600,
    }


def _reading_app(service: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(reading_router)
    app.dependency_overrides[reading_get_session_service] = lambda: service
    return app


def _internal_app() -> FastAPI:
    app = FastAPI()
    app.include_router(internal_router)
    return app


@pytest.mark.asyncio
async def test_reading_academic_full_flow(
    exam_base_url: str, internal_headers: dict[str, str]
) -> None:
    service = FakeReadingSessionService()
    app = _reading_app(service)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=exam_base_url) as client:
        start_response = await client.get(
            f"/exam/reading/start?exam_type=academic&user_id={uuid4()}",
            headers=internal_headers,
        )
        assert start_response.status_code == 200
        data = start_response.json()
        assert data["session_id"] == str(service.session_id)

        submit_response = await client.put(
            f"/exam/reading/{service.session_id}/submit",
            headers=internal_headers,
            json={"answers": _correct_reading_answers()},
        )
        assert submit_response.status_code == 200
        result = submit_response.json()
        assert result["raw_score"] == 40
        assert result["band_score"] == 9.0


@pytest.mark.asyncio
async def test_reading_expired_session_returns_403(
    exam_base_url: str, internal_headers: dict[str, str]
) -> None:
    expired_session = _build_expired_reading_session()
    question = {
        "id": expired_session["question_id"],
        "book_ref": "test-book",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "reading",
        "passage_text": "Passage 1\n---\nPassage 2\n---\nPassage 3",
        "audio_s3_key": None,
        "questions": [{"id": str(i), "prompt": f"Q{i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }

    service = SessionService(
        session_repository=FakeSessionRepository(expired_session),
        question_repository=FakeQuestionRepository(question),
        result_repository=FakeResultRepository(),
        timer_service=TimerService(),
    )
    app = _reading_app(service)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=exam_base_url) as client:
        response = await client.put(
            f"/exam/reading/{expired_session['id']}/submit",
            headers=internal_headers,
            json={"answers": _correct_reading_answers()},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_speaking_academic_flow_asserts_criterion_bands(
    exam_base_url: str, internal_headers: dict[str, str]
) -> None:
    fake_session_repo = type(
        "FakeSessionRepository",
        (),
        {
            "__init__": lambda self: None,
            "get_by_id": AsyncMock(return_value={
                "id": uuid4(),
                "user_id": uuid4(),
                "skill_area": "speaking",
                "status": "in_progress",
                "exam_type": "academic",
                "question_id": None,
            }),
            "try_submit": AsyncMock(return_value=True),
            "mark_scored": AsyncMock(),
        },
    )()

    fake_transcript_repo = type(
        "FakeTranscriptRepository",
        (),
        {
            "__init__": lambda self: setattr(self, "transcripts", []),
            "create_or_update": AsyncMock(return_value=None),
            "get_all_for_session": AsyncMock(return_value=[
                {"part": 1, "transcript_text": "one"},
                {"part": 2, "transcript_text": "two"},
                {"part": 3, "transcript_text": "three"},
            ]),
        },
    )()

    fake_result_repo = type(
        "FakeResultRepository",
        (),
        {
            "__init__": lambda self: setattr(self, "created", None),
            "create": AsyncMock(return_value=None),
        },
    )()

    evaluation = {
        "status": "completed",
        "partial": False,
        "overall_band": 8.5,
        "dimensions": {
            "fluency": {
                "criterion": "fluency",
                "band": 8.0,
                "overall_feedback": "Good",
                "part_notes": {"Part 1": "Good"},
                "examples": [{"part": 1, "quote": "q", "issue": "i"}],
                "improvement_tip": "tip",
                "timed_out": False,
            },
            "lexical": {
                "criterion": "lexical",
                "band": 8.0,
                "overall_feedback": "Good",
                "part_notes": {"Part 1": "Good"},
                "examples": [{"part": 1, "quote": "q", "issue": "i"}],
                "improvement_tip": "tip",
                "timed_out": False,
            },
            "grammar": {
                "criterion": "grammar",
                "band": 8.0,
                "overall_feedback": "Good",
                "part_notes": {"Part 1": "Good"},
                "examples": [{"part": 1, "quote": "q", "issue": "i"}],
                "improvement_tip": "tip",
                "timed_out": False,
            },
            "pronunciation": {
                "criterion": "pronunciation",
                "band": 8.0,
                "overall_feedback": "Good",
                "part_notes": {"Part 1": "Good"},
                "examples": [{"part": 1, "quote": "q", "issue": "i"}],
                "improvement_tip": "tip",
                "timed_out": False,
            },
        },
        "overall_feedback": "Excellent",
    }

    with patch("app.api.internal.SessionRepository", return_value=fake_session_repo), patch(
        "app.api.internal.TranscriptRepository", return_value=fake_transcript_repo
    ), patch("app.api.internal.ResultRepository", return_value=fake_result_repo), patch(
        "app.api.internal.SpeakingServiceClient"
    ) as mock_speaking_client:
        mock_client_instance = mock_speaking_client.return_value
        mock_client_instance.evaluate_holistic = AsyncMock(return_value=evaluation)

        app = _internal_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=exam_base_url) as client:
            session_id = fake_session_repo.get_by_id.return_value["id"]

            for part in (1, 2):
                response = await client.post(
                    f"/internal/sessions/{session_id}/speaking/transcripts",
                    headers=internal_headers,
                    json={
                        "part": part,
                        "transcript_text": f"part-{part}",
                        "duration_s": 60,
                        "question_text": f"question-{part}",
                    },
                )
                assert response.status_code == 200

            response = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=internal_headers,
                json={
                    "part": 3,
                    "transcript_text": "part-3",
                    "duration_s": 120,
                    "question_text": "question-3",
                },
            )
            assert response.status_code == 200

    create_call = fake_result_repo.create
    assert create_call.called, "Speaking result should have been persisted"
    created_kwargs = create_call.call_args.kwargs
    assert created_kwargs["band_score"] == 8.5
    assert set(created_kwargs["section_scores"]) == {
        "fluency",
        "lexical",
        "grammar",
        "pronunciation",
    }
    assert created_kwargs["agent_responses"]["overall_band"] == 8.5
    assert set(created_kwargs["agent_responses"]["dimensions"]) == {
        "fluency",
        "lexical",
        "grammar",
        "pronunciation",
    }


@pytest.mark.skip(reason="Blocked by missing S3/Seed data (BUG-050/BUG-023)")
def test_listening_academic_flow_blocked() -> None:
    pass


@pytest.mark.skip(reason="Blocked by missing S3/Seed data (BUG-050/BUG-023)")
def test_writing_academic_flow_blocked() -> None:
    pass


@pytest.mark.skip(reason="Blocked by missing S3/Seed data (BUG-050/BUG-023)")
def test_writing_general_flow_blocked() -> None:
    pass
