from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from prometheus_client import make_asgi_app

from app.api.listening import get_session_service, router as listening_router
from app.services.audio_delivery_service import (
    ListeningAudioUnavailableError,
    S3AudioDeliveryService,
)
from app.services.grading_service import GradingService
from app.services.session_service import SessionService


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


class FakeS3Client:
    """Fake S3 with a real notion of which objects exist.

    `missing_keys` is the point of this fake. The delivery service now HEADs each
    section before pre-signing it, because pre-signing never touches S3 and so
    happily produced four valid URLs against an entirely empty bucket (BUG-022).
    A fake that reports every object as present cannot catch a regression of
    that, so absence has to be representable here.
    """

    def __init__(self, missing_keys: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.head_calls: list[str] = []
        self.missing_keys = missing_keys or set()

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        self.head_calls.append(Key)
        if Key in self.missing_keys:
            raise RuntimeError(f"404 Not Found: {Key}")
        return {"ContentLength": 1024}

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.calls.append({"operation": operation, **kwargs})
        key = kwargs["Params"]["Key"]
        return f"https://audio.example/{key}?signature={len(self.calls)}"


def test_empty_bucket_is_refused_rather_than_signed() -> None:
    """The exact BUG-022 scenario: bucket has nothing in it.

    Before the guard this returned four well-formed URLs and a 200, and the
    candidate got a session, a 40-minute clock and four 404s on play.
    """
    all_sections = {
        f"exam-audio/IELTS-18/1/section{n}.mp3" for n in range(1, 5)
    }
    s3 = FakeS3Client(missing_keys=all_sections)
    service = S3AudioDeliveryService(s3, "goa-exam-audio")

    with pytest.raises(ListeningAudioUnavailableError) as exc:
        service.generate_section_urls("exam-audio/IELTS-18/1/section1.mp3", uuid4())

    assert "4 of 4" in str(exc.value)
    # Nothing may be signed once a section is known missing.
    assert s3.calls == []


def test_partially_uploaded_audio_is_refused_and_names_the_missing_section() -> None:
    """A half-populated bucket is the more likely production shape.

    Three playable sections and one 404 is worse than none, because it fails
    only after the candidate has started and burned part of the clock.
    """
    s3 = FakeS3Client(missing_keys={"exam-audio/IELTS-18/1/section3.mp3"})
    service = S3AudioDeliveryService(s3, "goa-exam-audio")

    with pytest.raises(ListeningAudioUnavailableError) as exc:
        service.generate_section_urls("exam-audio/IELTS-18/1/section1.mp3", uuid4())

    message = str(exc.value)
    assert "1 of 4" in message
    assert "section3.mp3" in message
    assert s3.calls == []


def test_all_four_sections_are_checked_before_any_is_signed() -> None:
    s3 = FakeS3Client()
    service = S3AudioDeliveryService(s3, "goa-exam-audio")

    service.generate_section_urls("exam-audio/IELTS-18/1/section1.mp3", uuid4())

    assert s3.head_calls == [
        f"exam-audio/IELTS-18/1/section{n}.mp3" for n in range(1, 5)
    ]


def test_presigned_urls_use_four_section_keys_and_7200_second_expiry() -> None:
    s3 = FakeS3Client()
    service = S3AudioDeliveryService(s3, "goa-exam-audio")
    session_id = uuid4()

    urls = service.generate_section_urls(
        "exam-audio/IELTS-18/1/section1.mp3",
        session_id,
    )

    assert len(urls) == 4
    assert [call["Params"]["Key"] for call in s3.calls] == [
        f"exam-audio/IELTS-18/1/section{i}.mp3" for i in range(1, 5)
    ]
    assert all(call["operation"] == "get_object" for call in s3.calls)
    assert all(call["ExpiresIn"] == 7200 for call in s3.calls)
    assert all(
        str(session_id) in call["Params"]["ResponseContentDisposition"]
        for call in s3.calls
    )


def test_listening_grading_known_answer_set_and_section_breakdown() -> None:
    answer_key = {str(i): f"ANSWER{i}" for i in range(1, 41)}
    submitted = {str(i): f"answer{i}" if i <= 30 else "wrong" for i in range(1, 41)}

    result = GradingService().grade_listening(submitted, answer_key)

    assert result["raw_score"] == 30
    assert result["band_score"] == 7.0
    assert result["section_breakdown"] == {
        "section_1": {"correct": 10, "total": 10},
        "section_2": {"correct": 10, "total": 10},
        "section_3": {"correct": 10, "total": 10},
        "section_4": {"correct": 0, "total": 10},
    }
    assert len(result["per_question_result"]) == 40


def test_listening_grading_accepts_either_order_without_duplicate_credit() -> None:
    answer_key = {
        "answers": {"21": "B", "22": "D"},
        "unordered_groups": [["21", "22"]],
    }
    grader = GradingService()

    reversed_result = grader.grade_listening(
        {"21": "D", "22": "B"},
        answer_key,
    )
    duplicate_result = grader.grade_listening(
        {"21": "B", "22": "B"},
        answer_key,
    )

    assert reversed_result["raw_score"] == 2
    assert duplicate_result["raw_score"] == 1
    assert reversed_result["per_question_result"]["21"]["correct_answer"] == "B / D"


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
            self.session if self.session and self.session["id"] == session_id else None
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


def _question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "audio_s3_key": "exam-audio/IELTS-18/1/section1.mp3",
        "questions": [{"id": str(i), "prompt": f"Question {i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }


@pytest.mark.asyncio
async def test_start_and_submit_listening_session_integration() -> None:
    user_id = uuid4()
    session_repository = FakeSessionRepository()
    result_repository = FakeResultRepository()
    audio = S3AudioDeliveryService(FakeS3Client(), "goa-exam-audio")
    service = SessionService(
        session_repository=session_repository,
        question_repository=FakeQuestionRepository(_question()),
        result_repository=result_repository,
        audio_delivery_service=audio,
    )

    started = await service.create_listening_session(user_id, "academic")
    result = await service.submit_listening_session(
        session_id=started["session_id"],
        user_id=user_id,
        answers={str(i): f"A{i}" for i in range(1, 41)},
    )

    assert len(started["audio_urls"]) == 4
    assert len(started["questions"]) == 40
    assert started["time_limit_seconds"] == 2400
    assert started["audio_url_expiry_seconds"] == 7200
    assert result["raw_score"] == 40
    assert result["band_score"] == 9.0
    assert result_repository.saved is not None


@pytest.mark.asyncio
async def test_submit_rejects_a_different_session_owner() -> None:
    owner_id = uuid4()
    session_repository = FakeSessionRepository()
    service = SessionService(
        session_repository=session_repository,
        question_repository=FakeQuestionRepository(_question()),
        result_repository=FakeResultRepository(),
        audio_delivery_service=S3AudioDeliveryService(FakeS3Client(), "goa-exam-audio"),
    )
    started = await service.create_listening_session(owner_id, "academic")

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_listening_session(
            started["session_id"],
            uuid4(),
            {"1": "A1"},
        )

    assert exc_info.value.status_code == 403


class FakeListeningSessionService:
    async def create_listening_session(
        self, user_id: UUID, exam_type: str
    ) -> dict[str, Any]:
        return {
            "session_id": uuid4(),
            "audio_urls": [f"https://audio.example/section{i}" for i in range(1, 5)],
            "questions": [{"id": str(i)} for i in range(1, 41)],
            "time_limit_seconds": 2400,
            "audio_url_expiry_seconds": 7200,
        }

    async def submit_listening_session(
        self, session_id: UUID, user_id: UUID, answers: dict[str, str]
    ) -> dict[str, Any]:
        return {
            "raw_score": 1,
            "band_score": 0.0,
            "per_question_result": {},
            "section_breakdown": {
                f"section_{i}": {"correct": 0, "total": 10} for i in range(1, 5)
            },
        }


def test_listening_api_full_flow_returns_expected_contract() -> None:
    app = FastAPI()
    app.include_router(listening_router)
    app.mount("/metrics", make_asgi_app())
    app.dependency_overrides[get_session_service] = FakeListeningSessionService
    client = TestClient(app)
    user_id = uuid4()

    started = client.get(
        f"/exam/listening/start?user_id={user_id}", headers=INTERNAL_HEADERS
    )
    assert started.status_code == 200
    assert len(started.json()["audio_urls"]) == 4
    assert len(started.json()["questions"]) == 40

    submitted = client.put(
        f"/exam/listening/{started.json()['session_id']}/submit?user_id={user_id}",
        headers=INTERNAL_HEADERS,
        json={"answers": {"1": "A1"}},
    )
    assert submitted.status_code == 200
    assert set(submitted.json()) == {
        "raw_score",
        "band_score",
        "per_question_result",
        "section_breakdown",
    }

    metrics = client.get("/metrics").text
    assert "goa_exam_listening_sessions_total" in metrics
    assert "goa_exam_listening_score" in metrics
    assert 'goa_exam_grading_latency_ms_count{skill_area="listening"}' in metrics
