"""Remaining in-scope GOA-066 completion tests for the Exam service.

Covers the exam-completion observability contract on the listening path, the
"exactly once per completed session" guarantee, and the robustness fix that
keeps a completion log from crashing an already-scored submission when the
question metadata is missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from prometheus_client import REGISTRY
from structlog.testing import capture_logs

from app.services.audio_delivery_service import S3AudioDeliveryService
from app.services.session_service import SessionService
from tests.test_listening_exam import (
    FakeQuestionRepository,
    FakeResultRepository,
    FakeS3Client,
    FakeSessionRepository,
)


def _question(book_ref: str | None = "IELTS-18") -> dict[str, Any]:
    q: dict[str, Any] = {
        "id": uuid4(),
        "audio_s3_key": "exam-audio/IELTS-18/1/section1.mp3",
        "questions": [{"id": str(i), "prompt": f"Q{i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }
    if book_ref is not None:
        q["book_ref"] = book_ref
    return q


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _service(question: dict[str, Any]) -> tuple[SessionService, FakeSessionRepository]:
    session_repo = FakeSessionRepository()
    service = SessionService(
        session_repository=session_repo,
        question_repository=FakeQuestionRepository(question),
        result_repository=FakeResultRepository(),
        audio_delivery_service=S3AudioDeliveryService(FakeS3Client(), "goa-exam-audio"),
    )
    return service, session_repo


@pytest.mark.asyncio
async def test_listening_completion_emits_log_and_score_distribution() -> None:
    user_id = uuid4()
    service, _ = _service(_question())
    labels = {"skill_area": "listening", "exam_type": "academic"}
    before = _sample("goa_exam_score_distribution_count", labels) or 0.0

    started = await service.create_listening_session(user_id, "academic")

    with capture_logs() as logs:
        await service.submit_listening_session(
            session_id=started["session_id"],
            user_id=user_id,
            answers={str(i): f"A{i}" for i in range(1, 41)},
        )

    completion = [log for log in logs if log["event"] == "exam_completed"]
    assert len(completion) == 1
    assert completion[0]["skill_area"] == "listening"
    assert completion[0]["exam_type"] == "academic"
    assert completion[0]["band_score"] == 9.0
    assert completion[0]["question_bank_ref"] == "IELTS-18"

    assert _sample("goa_exam_score_distribution_count", labels) == before + 1


@pytest.mark.asyncio
async def test_completion_is_recorded_exactly_once_per_session() -> None:
    # A second submit of a scored listening session is rejected (409) before it
    # can reach the completion path, so the log and histogram move exactly once.
    user_id = uuid4()
    service, _ = _service(_question())
    labels = {"skill_area": "listening", "exam_type": "academic"}
    before = _sample("goa_exam_score_distribution_count", labels) or 0.0

    started = await service.create_listening_session(user_id, "academic")
    answers = {str(i): f"A{i}" for i in range(1, 41)}

    with capture_logs() as logs:
        await service.submit_listening_session(
            session_id=started["session_id"], user_id=user_id, answers=answers
        )
        with pytest.raises(HTTPException) as exc:
            await service.submit_listening_session(
                session_id=started["session_id"], user_id=user_id, answers=answers
            )

    assert exc.value.status_code == 409
    completion = [log for log in logs if log["event"] == "exam_completed"]
    assert len(completion) == 1
    assert _sample("goa_exam_score_distribution_count", labels) == before + 1


@pytest.mark.asyncio
async def test_completion_survives_a_question_missing_book_ref() -> None:
    # Regression: the completion log must never crash an already-scored
    # submission. A question row without book_ref logs None, not KeyError/500.
    user_id = uuid4()
    service, _ = _service(_question(book_ref=None))

    started = await service.create_listening_session(user_id, "academic")

    with capture_logs() as logs:
        result = await service.submit_listening_session(
            session_id=started["session_id"],
            user_id=user_id,
            answers={str(i): f"A{i}" for i in range(1, 41)},
        )

    # The grading result is returned normally.
    assert result["band_score"] == 9.0
    entry = next(log for log in logs if log["event"] == "exam_completed")
    assert entry["question_bank_ref"] is None
