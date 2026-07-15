from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import make_asgi_app

from app.api.questions import get_question_repository, router as questions_router
from app.api.sessions import get_session_service, router as sessions_router


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


class FakeSessionService:
    def __init__(self) -> None:
        self.session_id = uuid4()

    async def create_session(self, request: Any) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "first_question_set": _public_question(),
        }

    async def get_session(self, session_id: Any) -> dict[str, Any]:
        return {
            "id": session_id,
            "user_id": uuid4(),
            "exam_type": "academic",
            "skill_area": "reading",
            "status": "in_progress",
            "started_at": None,
            "submitted_at": None,
            "time_limit_seconds": 3600,
            "remaining_seconds": 3500,
            "questions": [_public_question()],
        }

    async def submit_session(self, session_id: Any, request: Any) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "status": "submitted",
            "raw_score": 1,
            "band_score": 4.5,
        }

    async def get_result(self, session_id: Any) -> dict[str, Any]:
        return {
            "id": uuid4(),
            "session_id": session_id,
            "user_id": uuid4(),
            "skill_area": "reading",
            "raw_score": 1,
            "band_score": 4.5,
            "section_scores": {"overall": {"correct": 1, "total": 1}},
            "graded_at": "2026-06-30T00:00:00Z",
            "answer_key": {"answers": {"1": "A"}},
        }


class FakeQuestionRepository:
    async def get_random_question(self, exam_type: str, skill_area: str, user_id: Any) -> dict[str, Any]:
        question = _public_question()
        question["answer_key"] = {"answers": {"1": "A"}}
        return question


def test_answer_key_is_absent_before_submission() -> None:
    client = _client()

    response = client.post(
        "/sessions",
        headers=INTERNAL_HEADERS,
        json={
            "user_id": str(uuid4()),
            "exam_type": "academic",
            "skill_area": "reading",
        },
    )

    assert response.status_code == 200
    assert "answer_key" not in response.json()["first_question_set"]


def test_create_session_submit_answers_and_retrieve_result() -> None:
    client = _client()
    session_id = str(uuid4())

    create_response = client.post(
        "/sessions",
        headers=INTERNAL_HEADERS,
        json={
            "user_id": str(uuid4()),
            "exam_type": "academic",
            "skill_area": "reading",
        },
    )
    submit_response = client.put(
        f"/sessions/{session_id}/submit",
        headers=INTERNAL_HEADERS,
        json={"answers": {"1": "A"}},
    )
    result_response = client.get(
        f"/sessions/{session_id}/result",
        headers=INTERNAL_HEADERS,
    )

    assert create_response.status_code == 200
    assert submit_response.status_code == 200
    assert result_response.status_code == 200
    assert result_response.json()["answer_key"] == {"answers": {"1": "A"}}


def test_metrics_endpoint_contains_exam_sessions_counter() -> None:
    client = _client()
    session_id = str(uuid4())

    client.put(
        f"/sessions/{session_id}/submit",
        headers=INTERNAL_HEADERS,
        json={"answers": {"1": "A"}},
    )
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "goa_exam_sessions_total" in response.text


def test_random_question_does_not_expose_answer_key() -> None:
    client = _client()

    response = client.get(
        f"/questions/random?exam_type=academic&skill_area=reading&user_id={uuid4()}",
        headers=INTERNAL_HEADERS,
    )

    assert response.status_code == 200
    assert "answer_key" not in response.json()


def test_internal_api_key_is_required() -> None:
    client = _client()

    response = client.get("/sessions/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 401


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(sessions_router)
    app.include_router(questions_router)
    app.mount("/metrics", make_asgi_app())
    app.dependency_overrides[get_session_service] = FakeSessionService
    app.dependency_overrides[get_question_repository] = FakeQuestionRepository
    return TestClient(app)


def _public_question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "book-1",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "reading",
        "passage_text": "Passage",
        "audio_s3_key": None,
        "questions": [{"id": "1", "prompt": "Question"}],
    }
