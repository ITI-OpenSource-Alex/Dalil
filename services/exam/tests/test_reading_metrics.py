"""Integration tests for Reading exam metrics (GOA-066).

Drives the real reading start/submit flow through the router and
``SessionService`` (only the repositories are faked) and asserts that the
observability signals fire: the pre-existing grading-latency and reading-score
metrics on the router, plus the GOA-066 ``goa_exam_score_distribution``
histogram and the structured ``exam_completed`` log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, make_asgi_app
from structlog.testing import capture_logs

from app.api.reading import get_session_service, router as reading_router
from app.services.session_service import SessionService


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


class FakeQuestionRepository:
    def __init__(self, question: dict[str, Any]) -> None:
        self.question = question

    async def get_random_unseen_question(self, **kwargs: Any) -> dict[str, Any]:
        return self.question

    async def get_by_id(self, question_id: UUID) -> dict[str, Any]:
        return self.question


class FakeSessionRepository:
    def __init__(self) -> None:
        self.session: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> None:
        self.session = {
            "id": kwargs["session_id"],
            "started_at": datetime.now(timezone.utc),
            "submitted_at": None,
            **{key: value for key, value in kwargs.items() if key != "session_id"},
        }

    async def get_by_id(self, session_id: UUID) -> dict[str, Any] | None:
        return (
            self.session
            if self.session and self.session["id"] == session_id
            else None
        )

    async def submit(self, session_id: UUID) -> None:
        assert self.session is not None
        self.session["status"] = "submitted"

    async def mark_scored(self, session_id: UUID) -> None:
        assert self.session is not None
        self.session["status"] = "scored"


class FakeResultRepository:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> None:
        self.saved = kwargs


def _reading_question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "IELTS-18",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "reading",
        "passage_text": "Passage one\n---\nPassage two\n---\nPassage three",
        "audio_s3_key": None,
        "questions": [{"number": i, "prompt": f"Q{i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _build_app() -> tuple[TestClient, FakeSessionRepository, FakeResultRepository]:
    session_repo = FakeSessionRepository()
    result_repo = FakeResultRepository()

    def _service() -> SessionService:
        return SessionService(
            session_repository=session_repo,
            question_repository=FakeQuestionRepository(_reading_question()),
            result_repository=result_repo,
        )

    app = FastAPI()
    app.include_router(reading_router)
    app.mount("/metrics", make_asgi_app())
    app.dependency_overrides[get_session_service] = _service
    return TestClient(app), session_repo, result_repo


def test_reading_submit_exports_grading_latency_and_score_metrics() -> None:
    client, _, result_repo = _build_app()
    user_id = uuid4()

    started = client.get(
        f"/exam/reading/start?exam_type=academic&user_id={user_id}",
        headers=INTERNAL_HEADERS,
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]

    # All correct → band 9.0, a clean signal to look for in the histogram.
    answers = {str(i): f"A{i}" for i in range(1, 41)}
    submitted = client.put(
        f"/exam/reading/{session_id}/submit",
        headers=INTERNAL_HEADERS,
        json={"answers": answers},
    )
    assert submitted.status_code == 200
    assert result_repo.saved is not None

    metrics = client.get("/metrics").text
    # Pre-existing reading metrics (must keep working, GOA-066 does not touch).
    assert 'goa_exam_grading_latency_ms_count{skill_area="reading"}' in metrics
    assert "goa_exam_reading_score_count" in metrics
    # GOA-066 score-distribution histogram, labelled by skill + exam type.
    assert (
        'goa_exam_score_distribution_count{exam_type="academic",skill_area="reading"}'
        in metrics
    )


def test_reading_submit_records_band_into_score_distribution() -> None:
    client, _, _ = _build_app()
    user_id = uuid4()
    labels = {"skill_area": "reading", "exam_type": "academic"}

    before = _sample("goa_exam_score_distribution_count", labels) or 0.0

    started = client.get(
        f"/exam/reading/start?exam_type=academic&user_id={user_id}",
        headers=INTERNAL_HEADERS,
    )
    session_id = started.json()["session_id"]
    client.put(
        f"/exam/reading/{session_id}/submit",
        headers=INTERNAL_HEADERS,
        json={"answers": {str(i): f"A{i}" for i in range(1, 41)}},
    )

    after = _sample("goa_exam_score_distribution_count", labels)
    assert after == before + 1
    # Band 9.0 lands in the top finite bucket.
    assert _sample(
        "goa_exam_score_distribution_bucket", {**labels, "le": "9.0"}
    ) >= 1.0


def test_reading_submit_emits_completion_log_with_book_ref() -> None:
    client, _, _ = _build_app()
    user_id = uuid4()

    started = client.get(
        f"/exam/reading/start?exam_type=academic&user_id={user_id}",
        headers=INTERNAL_HEADERS,
    )
    session_id = started.json()["session_id"]

    with capture_logs() as logs:
        client.put(
            f"/exam/reading/{session_id}/submit",
            headers=INTERNAL_HEADERS,
            json={"answers": {str(i): f"A{i}" for i in range(1, 41)}},
        )

    completion = [log for log in logs if log["event"] == "exam_completed"]
    assert len(completion) == 1
    entry = completion[0]
    assert entry["skill_area"] == "reading"
    assert entry["exam_type"] == "academic"
    assert entry["band_score"] == 9.0
    assert entry["question_bank_ref"] == "IELTS-18"
    assert entry["session_id"] == str(session_id)
    assert isinstance(entry["duration_s"], float)
