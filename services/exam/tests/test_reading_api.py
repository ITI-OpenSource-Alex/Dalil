from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.reading import get_session_service, router as reading_router


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


class FakeReadingSessionService:
    def __init__(self) -> None:
        self.session_id = uuid4()

    async def create_reading_session(
        self, user_id: Any, exam_type: str
    ) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "passages": ["Passage 1", "Passage 2", "Passage 3"],
            "questions": [
                {"id": str(i), "prompt": f"Q{i}"} for i in range(1, 41)
            ],
            "time_limit_seconds": 3600,
        }

    async def submit_reading_session(
        self, session_id: Any, answers: dict[str, str]
    ) -> dict[str, Any]:
        return {
            "raw_score": 30,
            "band_score": 7.0,
            "per_question_result": {
                "1": {
                    "submitted_answer": "A",
                    "correct_answer": "A",
                    "is_correct": True,
                }
            },
            "section_breakdown": {
                "section_1": {"correct": 10, "total": 13},
                "section_2": {"correct": 10, "total": 13},
                "section_3": {"correct": 10, "total": 14},
            },
        }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(reading_router)
    app.dependency_overrides[get_session_service] = FakeReadingSessionService
    return TestClient(app)


def test_start_returns_questions_without_answer_key() -> None:
    client = _client()
    user_id = str(uuid4())

    response = client.get(
        f"/exam/reading/start?exam_type=academic&user_id={user_id}",
        headers=INTERNAL_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "passages" in data
    assert len(data["passages"]) == 3
    assert "questions" in data
    assert data["time_limit_seconds"] == 3600
    assert "answer_key" not in data


def test_submit_returns_full_result() -> None:
    client = _client()
    session_id = str(uuid4())

    response = client.put(
        f"/exam/reading/{session_id}/submit",
        headers=INTERNAL_HEADERS,
        json={"answers": {"1": "A"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["raw_score"] == 30
    assert data["band_score"] == 7.0
    assert "per_question_result" in data
    assert "section_breakdown" in data


def test_full_reading_flow() -> None:
    client = _client()
    user_id = str(uuid4())

    start_response = client.get(
        f"/exam/reading/start?exam_type=academic&user_id={user_id}",
        headers=INTERNAL_HEADERS,
    )
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    submit_response = client.put(
        f"/exam/reading/{session_id}/submit",
        headers=INTERNAL_HEADERS,
        json={"answers": {"1": "A"}},
    )
    assert submit_response.status_code == 200
    result = submit_response.json()
    assert "raw_score" in result
    assert "band_score" in result
    assert "per_question_result" in result
    assert "section_breakdown" in result


def test_internal_api_key_required() -> None:
    client = _client()
    user_id = str(uuid4())

    response = client.get(
        f"/exam/reading/start?exam_type=academic&user_id={user_id}",
    )
    assert response.status_code == 401
