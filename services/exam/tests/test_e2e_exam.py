"""
E2E Test Suite for the IELTS Exam Microservice.
12 test cases covering reading, listening, speaking, writing, and metrics flows.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry, make_asgi_app

from app.api.reading import get_session_service as reading_get_session_service
from app.api.reading import router as reading_router
from app.api.listening import (
    get_session_service as listening_get_session_service,
    router as listening_router,
)
from app.api.sessions import get_session_service as sessions_get_session_service
from app.api.sessions import router as sessions_router
from app.api.internal import router as internal_router
from app.services.audio_delivery_service import S3AudioDeliveryService
from app.services.session_service import SessionService
from app.services.writing_client import ExamTaskEvaluationResponse, WritingClient


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}
BASE_URL = "http://test"


# ---------------------------------------------------------------------------
# Fake Repositories
# ---------------------------------------------------------------------------


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, dict[str, Any]] = {}

    async def create(self, **kwargs: Any) -> None:
        sid = kwargs["session_id"]
        self.sessions[sid] = {
            "id": sid,
            "user_id": kwargs["user_id"],
            "question_id": kwargs["question_id"],
            "exam_type": kwargs["exam_type"],
            "skill_area": kwargs["skill_area"],
            "status": kwargs.get("status", "in_progress"),
            "started_at": datetime.now(timezone.utc),
            "submitted_at": None,
            "time_limit_seconds": kwargs.get("time_limit_seconds", 3600),
        }

    async def get_by_id(self, session_id: UUID) -> dict[str, Any] | None:
        return self.sessions.get(session_id)

    async def submit(self, session_id: UUID) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "submitted"
            self.sessions[session_id]["submitted_at"] = datetime.now(timezone.utc)

    async def mark_scored(self, session_id: UUID) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "scored"

    async def try_submit(self, session_id: UUID) -> bool:
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "submitted"
            return True
        return False


class FakeQuestionRepository:
    def __init__(self, question: dict[str, Any]) -> None:
        self.question = question

    async def get_random_unseen_question(self, **kwargs: Any) -> dict[str, Any] | None:
        return self.question

    async def get_random_question(self, **kwargs: Any) -> dict[str, Any] | None:
        return self.question

    async def get_by_id(self, question_id: Any) -> dict[str, Any] | None:
        return self.question


class FakeResultRepository:
    def __init__(self) -> None:
        self.results: dict[UUID, dict[str, Any]] = {}

    async def create(self, **kwargs: Any) -> None:
        sid = kwargs.get("session_id")
        self.results[sid] = kwargs

    async def get_by_session(self, session_id: UUID) -> dict[str, Any] | None:
        return self.results.get(session_id)


class FakeWritingResponseRepository:
    def __init__(self) -> None:
        self.responses: dict[tuple[UUID, int], dict[str, Any]] = {}

    async def save_response(
        self,
        session_id: UUID,
        task_number: int,
        response_text: str,
        word_count: int,
        penalty_flag: bool,
    ) -> None:
        self.responses[(session_id, task_number)] = {
            "session_id": session_id,
            "task_number": task_number,
            "response_text": response_text,
            "word_count": word_count,
            "penalty_flag": penalty_flag,
            "evaluation_result": None,
        }

    async def save_evaluation(
        self, session_id: UUID, task_number: int, evaluation_result: dict[str, Any]
    ) -> None:
        key = (session_id, task_number)
        if key in self.responses:
            import json

            self.responses[key]["evaluation_result"] = json.dumps(evaluation_result)

    async def get_all_by_session(self, session_id: UUID) -> list[dict[str, Any]]:
        return [
            v for k, v in self.responses.items() if k[0] == session_id
        ]

    async def get_by_session_and_task(
        self, session_id: UUID, task_number: int
    ) -> dict[str, Any] | None:
        return self.responses.get((session_id, task_number))


class FakeS3Client:
    def __init__(self, missing_keys: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.missing_keys = missing_keys or set()

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        # The delivery service HEADs each section before signing it, so a bucket
        # with no audio is refused rather than yielding four URLs that 404 on
        # play (BUG-022). This fake reports objects present by default; the
        # absent case is covered directly in test_listening_exam.py.
        if Key in self.missing_keys:
            raise RuntimeError(f"404 Not Found: {Key}")
        return {"ContentLength": 1024}

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.calls.append({"operation": operation, **kwargs})
        key = kwargs["Params"]["Key"]
        return f"https://audio.example/{key}?sig={len(self.calls)}"


class FakeWritingClient:
    def __init__(self, responses: dict[int, ExamTaskEvaluationResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def evaluate_exam_essay(self, **kwargs: Any) -> ExamTaskEvaluationResponse:
        self.calls.append(kwargs)
        task_number = kwargs["task_number"]
        return self.responses[task_number]


# ---------------------------------------------------------------------------
# Question Fixtures
# ---------------------------------------------------------------------------


def _reading_question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "IELTS-18",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "reading",
        "passage_text": "Passage one content.\n---\nPassage two content.\n---\nPassage three content.",
        "audio_s3_key": None,
        "questions": [{"id": str(i), "prompt": f"Question {i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }


def _listening_question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "IELTS-18",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "listening",
        "passage_text": None,
        "audio_s3_key": "exam-audio/IELTS-18/1/section1.mp3",
        "questions": [{"id": str(i), "prompt": f"Question {i}"} for i in range(1, 41)],
        "answer_key": {str(i): f"A{i}" for i in range(1, 41)},
    }


def _writing_question_academic() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "IELTS-18",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "writing",
        "passage_text": None,
        "audio_s3_key": None,
        "questions": {
            "task1": {
                "prompt": "Describe the chart below.",
                "image_s3_key": "writing-stimuli/ielts18-test1-task1.png",
            },
            "task2": {
                "prompt": "Some people think that technology is making life more complex. Discuss.",
            },
        },
        "answer_key": {},
    }


def _writing_question_general() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "IELTS-18",
        "test_number": 1,
        "exam_type": "general",
        "skill_area": "writing",
        "passage_text": None,
        "audio_s3_key": None,
        "questions": {
            "task1": {
                "prompt": "Write a letter to your landlord about a problem with your apartment.",
            },
            "task2": {
                "prompt": "Some people think that technology is making life more complex. Discuss.",
            },
        },
        "answer_key": {},
    }


def _writing_question_ingested_list_shape(
    exam_type: str = "academic",
) -> dict[str, Any]:
    """
    A writing question in the shape real ingestion produces.

    app/ingestion/writing_parser.py emits `questions` as a LIST of
    {number, prompt, question_type, instructions} — never the task1/task2 dict
    the fixtures above use. Every session created from a seeded Cambridge book
    therefore looks like this, and nothing in the suite covered it, which is how
    an AttributeError in _resolve_task_context reached production as a 500 on
    every writing submit.

    Note there is no image key anywhere: stimulus images are not ingested, which
    is why image-based evaluation is postponed.
    """
    return {
        "id": uuid4(),
        "book_ref": "IELTS-14",
        "test_number": 1,
        "exam_type": exam_type,
        "skill_area": "writing",
        "passage_text": None,
        "audio_s3_key": None,
        "questions": [
            {
                "number": 1,
                "prompt": "The charts below show the average percentages in typical meals.",
                "question_type": "Writing Task 1",
                "instructions": "Write at least 150 words.",
                "passage_number": None,
                "section_number": None,
            },
            {
                "number": 2,
                "prompt": "Some people believe it is best to accept a bad situation.",
                "question_type": "Writing Task 2",
                "instructions": "Write an essay of at least 250 words.",
                "passage_number": None,
                "section_number": None,
            },
        ],
        "answer_key": {},
    }


def _speaking_question() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "book_ref": "IELTS-18",
        "test_number": 1,
        "exam_type": "academic",
        "skill_area": "speaking",
        "passage_text": None,
        "audio_s3_key": None,
        "questions": [
            {"part": 1, "questions": ["What is your name?", "Where are you from?"]},
            {"part": 2, "topic": "Describe a book", "bullet_points": ["title", "author"]},
            {"part": 3, "questions": ["Do you think reading is important?"]},
        ],
        "answer_key": {},
    }


def _writing_eval_response(
    session_id: UUID, task_number: int, overall_band: float
) -> ExamTaskEvaluationResponse:
    """
    Mirrors the shape the Writing service genuinely returns:
    `inline_issues` with `issue_type`/`start_char`/`end_char`
    (services/writing/app/schemas.py). This fixture previously used
    `highlighted_issues`, a spelling the Writing service has never emitted,
    which is why the real contract mismatch went unnoticed by these tests.
    """
    return ExamTaskEvaluationResponse(
        essay_id=1,
        exam_session_id=str(session_id),
        task_number=task_number,
        evaluations=[
            {
                "criterion": "task_response",
                "band_score": overall_band,
                "feedback": "Good response.",
                "improvement_tip": "Address every bullet point.",
                "word_count": 160,
                "inline_issues": [],
            },
            {
                "criterion": "cohesion",
                "band_score": overall_band,
                "feedback": "Well structured.",
                "improvement_tip": "Vary your linking phrases.",
                "word_count": 160,
                "inline_issues": [],
            },
            {
                "criterion": "vocabulary",
                "band_score": overall_band,
                "feedback": "Good range.",
                "improvement_tip": "Avoid repeating 'important'.",
                "word_count": 160,
                "inline_issues": [],
            },
            {
                "criterion": "grammar",
                "band_score": overall_band,
                "feedback": "Accurate usage.",
                "improvement_tip": "Check article use.",
                "word_count": 160,
                "inline_issues": [
                    {
                        "text": "have went",
                        "issue_type": "Incorrect past participle",
                        "suggestion": "have gone",
                        "start_char": 0,
                        "end_char": 9,
                    }
                ],
            },
        ],
        overall_band=overall_band,
        from_cache=False,
    )


# ---------------------------------------------------------------------------
# TestReadingEngine — EXM-01, EXM-02, EXM-03
# ---------------------------------------------------------------------------


class TestReadingEngine:
    """Tests for reading exam start, submit, and timer expiry."""

    def _make_app(self, service: SessionService) -> FastAPI:
        app = FastAPI()
        app.include_router(reading_router)
        app.dependency_overrides[reading_get_session_service] = lambda: service
        return app

    def _make_service(
        self,
        question: dict[str, Any] | None = None,
        elapsed_seconds: float = 100.0,
        session_status: str = "in_progress",
    ) -> SessionService:
        q = question or _reading_question()
        session_repo = FakeSessionRepository()
        return SessionService(
            session_repository=session_repo,
            question_repository=FakeQuestionRepository(q),
            result_repository=FakeResultRepository(),
        )

    @pytest.mark.asyncio
    async def test_exm01_reading_start_returns_structure(self) -> None:
        """EXM-01: GET /exam/reading/start returns 3 passages, 40 questions, no answer_key, 3600s timer."""
        service = self._make_service()
        app = self._make_app(service)
        user_id = uuid4()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(
                f"/exam/reading/start?exam_type=academic&user_id={user_id}",
                headers=INTERNAL_HEADERS,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["passages"]) == 3
        assert len(data["questions"]) == 40
        assert data["time_limit_seconds"] == 3600
        assert "answer_key" not in data

    @pytest.mark.asyncio
    async def test_exm02_reading_submit_all_correct(self) -> None:
        """EXM-02: PUT /exam/reading/{id}/submit with all correct → raw_score=40, band_score=9.0."""
        service = self._make_service()
        app = self._make_app(service)
        user_id = uuid4()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            start_resp = await client.get(
                f"/exam/reading/start?exam_type=academic&user_id={user_id}",
                headers=INTERNAL_HEADERS,
            )
            session_id = start_resp.json()["session_id"]

            answers = {str(i): f"A{i}" for i in range(1, 41)}
            submit_resp = await client.put(
                f"/exam/reading/{session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={"answers": answers},
            )

        assert submit_resp.status_code == 200
        data = submit_resp.json()
        assert data["raw_score"] == 40
        assert data["band_score"] == 9.0
        assert "per_question_result" in data
        assert "section_breakdown" in data

    @pytest.mark.asyncio
    async def test_exm03_reading_submit_after_expiry_returns_403(self) -> None:
        """EXM-03: Submit after timer expiry (elapsed > limit + 30s grace) → 403."""
        question = _reading_question()
        session_repo = FakeSessionRepository()
        result_repo = FakeResultRepository()
        service = SessionService(
            session_repository=session_repo,
            question_repository=FakeQuestionRepository(question),
            result_repository=result_repo,
        )

        session_id = uuid4()
        started_at = datetime.now(timezone.utc) - timedelta(seconds=3631)
        session_repo.sessions[session_id] = {
            "id": session_id,
            "user_id": uuid4(),
            "question_id": question["id"],
            "exam_type": "academic",
            "skill_area": "reading",
            "status": "in_progress",
            "started_at": started_at,
            "submitted_at": None,
            "time_limit_seconds": 3600,
        }

        app = self._make_app(service)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.put(
                f"/exam/reading/{session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={"answers": {"1": "A1"}},
            )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestListeningEngine — EXM-04, EXM-05
# ---------------------------------------------------------------------------


class TestListeningEngine:
    """Tests for listening exam start (with presigned URLs) and grading."""

    def _make_service(self, question: dict[str, Any] | None = None) -> SessionService:
        q = question or _listening_question()
        s3 = FakeS3Client()
        audio_service = S3AudioDeliveryService(s3, "goa-exam-audio")
        return SessionService(
            session_repository=FakeSessionRepository(),
            question_repository=FakeQuestionRepository(q),
            result_repository=FakeResultRepository(),
            audio_delivery_service=audio_service,
        )

    def _make_app(self, service: SessionService) -> FastAPI:
        app = FastAPI()
        app.include_router(listening_router)
        app.dependency_overrides[listening_get_session_service] = lambda: service
        return app

    @pytest.mark.asyncio
    async def test_exm04_listening_start_returns_audio_urls(self) -> None:
        """EXM-04: GET /exam/listening/start returns 4 audio presigned URLs."""
        service = self._make_service()
        app = self._make_app(service)
        user_id = uuid4()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(
                f"/exam/listening/start?user_id={user_id}&exam_type=academic",
                headers=INTERNAL_HEADERS,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["audio_urls"]) == 4
        assert all("https://audio.example/" in url for url in data["audio_urls"])
        assert len(data["questions"]) == 40
        assert data["time_limit_seconds"] == 2400

    @pytest.mark.asyncio
    async def test_exm05_listening_submit_correct_band(self) -> None:
        """EXM-05: Submit all 40 correct listening answers → band_score=9.0."""
        service = self._make_service()
        app = self._make_app(service)
        user_id = uuid4()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            start_resp = await client.get(
                f"/exam/listening/start?user_id={user_id}&exam_type=academic",
                headers=INTERNAL_HEADERS,
            )
            session_id = start_resp.json()["session_id"]

            answers = {str(i): f"A{i}" for i in range(1, 41)}
            submit_resp = await client.put(
                f"/exam/listening/{session_id}/submit?user_id={user_id}",
                headers=INTERNAL_HEADERS,
                json={"answers": answers},
            )

        assert submit_resp.status_code == 200
        data = submit_resp.json()
        assert data["raw_score"] == 40
        assert data["band_score"] == 9.0
        assert data["section_breakdown"]["section_1"]["correct"] == 10
        assert data["section_breakdown"]["section_2"]["correct"] == 10
        assert data["section_breakdown"]["section_3"]["correct"] == 10
        assert data["section_breakdown"]["section_4"]["correct"] == 10


# ---------------------------------------------------------------------------
# TestSpeakingEngine — EXM-06, EXM-07
# ---------------------------------------------------------------------------


class TestSpeakingEngine:
    """Tests for speaking transcript submission and holistic evaluation."""

    def _client(self) -> httpx.AsyncClient:
        app = FastAPI()
        app.include_router(internal_router)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        )

    @pytest.mark.asyncio
    @patch("app.api.internal.SessionRepository")
    @patch("app.api.internal.TranscriptRepository")
    async def test_exm06_speaking_parts_1_2_return_empty(
        self, mock_transcript_repo: Any, mock_session_repo: Any
    ) -> None:
        """EXM-06: Speaking Parts 1 and 2 return {} with no feedback."""
        session_id = str(uuid4())

        mock_session_instance = mock_session_repo.return_value
        mock_session_instance.get_by_id = AsyncMock(
            return_value={
                "status": "in_progress",
                "user_id": uuid4(),
                "skill_area": "speaking",
            }
        )

        mock_transcript_instance = mock_transcript_repo.return_value
        mock_transcript_instance.create_or_update = AsyncMock()

        async with self._client() as client:
            resp1 = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=INTERNAL_HEADERS,
                json={
                    "part": 1,
                    "transcript_text": "My name is John and I come from London.",
                    "duration_s": 60,
                    "question_text": "What is your name?",
                },
            )
            assert resp1.status_code == 200
            assert resp1.json() == {}

            resp2 = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=INTERNAL_HEADERS,
                json={
                    "part": 2,
                    "transcript_text": "I would like to describe a book I read recently.",
                    "duration_s": 120,
                    "question_text": "Describe a book you enjoyed.",
                },
            )
            assert resp2.status_code == 200
            assert resp2.json() == {}

    @pytest.mark.asyncio
    @patch("app.api.internal.ResultRepository")
    @patch("app.api.internal.SpeakingServiceClient")
    @patch("app.api.internal.TranscriptRepository")
    @patch("app.api.internal.SessionRepository")
    async def test_exm07_speaking_part_3_triggers_holistic_eval(
        self,
        mock_session_repo: Any,
        mock_transcript_repo: Any,
        mock_speaking_client: Any,
        mock_result_repo: Any,
    ) -> None:
        """EXM-07: Part 3 triggers holistic eval with concatenated transcript and stores result."""
        session_id_uuid = uuid4()
        session_id = str(session_id_uuid)
        user_id = uuid4()

        mock_session_instance = mock_session_repo.return_value
        mock_session_instance.get_by_id = AsyncMock(
            return_value={
                "status": "in_progress",
                "user_id": user_id,
                "skill_area": "speaking",
            }
        )
        mock_session_instance.try_submit = AsyncMock(return_value=True)
        mock_session_instance.mark_scored = AsyncMock()

        mock_transcript_instance = mock_transcript_repo.return_value
        mock_transcript_instance.create_or_update = AsyncMock()
        mock_transcript_instance.get_all_for_session = AsyncMock(
            return_value=[
                {"part": 1, "transcript_text": "Part 1 answer."},
                {"part": 2, "transcript_text": "Part 2 long answer about a topic."},
                {"part": 3, "transcript_text": "Part 3 discussion response."},
            ]
        )

        eval_result = {
            "status": "completed",
            "partial": False,
            "overall_band": 7.5,
            "dimensions": {
                "fluency": {
                    "criterion": "fluency",
                    "band": 7.0,
                    "overall_feedback": "Good fluency with occasional hesitation.",
                    "part_notes": {"Part 1": "Smooth", "Part 2": "Good", "Part 3": "Slight hesitation"},
                    "examples": [{"part": 1, "quote": "I come from London", "issue": "minor pause"}],
                    "improvement_tip": "Practice speaking without pauses.",
                    "timed_out": False,
                },
                "lexical": {
                    "criterion": "lexical",
                    "band": 8.0,
                    "overall_feedback": "Wide range of vocabulary.",
                    "part_notes": {"Part 1": "Good", "Part 2": "Excellent", "Part 3": "Good"},
                    "examples": [{"part": 2, "quote": "comprehensive understanding", "issue": "good collocation"}],
                    "improvement_tip": "Use more idiomatic expressions.",
                    "timed_out": False,
                },
                "grammar": {
                    "criterion": "grammar",
                    "band": 7.5,
                    "overall_feedback": "Good grammatical range.",
                    "part_notes": {"Part 1": "Accurate", "Part 2": "Good", "Part 3": "Minor errors"},
                    "examples": [{"part": 3, "quote": "peoples", "issue": "irregular plural"}],
                    "improvement_tip": "Review irregular plurals.",
                    "timed_out": False,
                },
                "pronunciation": {
                    "criterion": "pronunciation",
                    "band": 7.5,
                    "overall_feedback": "Clear pronunciation.",
                    "part_notes": {"Part 1": "Clear", "Part 2": "Good", "Part 3": "Clear"},
                    "examples": [{"part": 1, "quote": "London", "issue": "clear articulation"}],
                    "improvement_tip": "Work on word stress.",
                    "timed_out": False,
                },
            },
            "overall_feedback": "Strong performance across all parts.",
        }
        mock_speaking_client_instance = mock_speaking_client.return_value
        mock_speaking_client_instance.evaluate_holistic = AsyncMock(
            return_value=eval_result
        )

        mock_result_instance = mock_result_repo.return_value
        mock_result_instance.create = AsyncMock()

        async with self._client() as client:
            resp = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=INTERNAL_HEADERS,
                json={
                    "part": 3,
                    "transcript_text": "Part 3 discussion response.",
                    "duration_s": 180,
                    "question_text": "Do you think reading is important?",
                },
            )

        assert resp.status_code == 200

        mock_speaking_client_instance.evaluate_holistic.assert_called_once()
        call_args = mock_speaking_client_instance.evaluate_holistic.call_args[0]
        payload = call_args[1]
        expected = "Part 1:\nPart 1 answer.\nPart 2:\nPart 2 long answer about a topic.\nPart 3:\nPart 3 discussion response."
        assert payload["concatenated_transcript"] == expected

        mock_result_instance.create.assert_called_once()
        create_kwargs = mock_result_instance.create.call_args[1]
        assert create_kwargs["band_score"] == 7.5
        assert create_kwargs["section_scores"] == {
            "fluency": 7.0,
            "lexical": 8.0,
            "grammar": 7.5,
            "pronunciation": 7.5,
        }
        assert create_kwargs["agent_responses"]["overall_band"] == 7.5
        assert "fluency" in create_kwargs["agent_responses"]["dimensions"]


# ---------------------------------------------------------------------------
# TestWritingEngine — EXM-08, EXM-09, EXM-10, EXM-11
# ---------------------------------------------------------------------------


class TestWritingEngine:
    """Tests for writing exam session creation, task submission, and band calculation."""

    def _make_service(
        self,
        question: dict[str, Any],
        writing_client: FakeWritingClient | None = None,
    ) -> tuple[SessionService, FakeSessionRepository, FakeWritingResponseRepository]:
        session_repo = FakeSessionRepository()
        question_repo = FakeQuestionRepository(question)
        result_repo = FakeResultRepository()
        writing_repo = FakeWritingResponseRepository()
        service = SessionService(
            session_repository=session_repo,
            question_repository=question_repo,
            result_repository=result_repo,
            writing_response_repository=writing_repo,
            writing_client=writing_client,
        )
        return service, session_repo, writing_repo

    def _make_app(self, service: SessionService) -> FastAPI:
        app = FastAPI()
        app.include_router(sessions_router)
        app.dependency_overrides[sessions_get_session_service] = lambda: service
        return app

    @pytest.mark.asyncio
    async def test_exm08_writing_session_start_academic(self) -> None:
        """EXM-08: POST /sessions with writing/academic returns session with task prompts."""
        question = _writing_question_academic()
        service, _, _ = self._make_service(question)
        app = self._make_app(service)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": str(uuid4()),
                    "exam_type": "academic",
                    "skill_area": "writing",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "first_question_set" in data
        questions = data["first_question_set"]["questions"]
        assert questions is not None

    @pytest.mark.asyncio
    async def test_exm09_writing_submit_task1_only(self) -> None:
        """EXM-09: Submit Task 1 → evaluated immediately, session still open."""
        question = _writing_question_academic()
        session_id = uuid4()
        task1_response = _writing_eval_response(session_id, 1, 7.0)
        writing_client = FakeWritingClient({1: task1_response})

        service, session_repo, _ = self._make_service(question, writing_client)
        app = self._make_app(service)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            create_resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": str(uuid4()),
                    "exam_type": "academic",
                    "skill_area": "writing",
                },
            )
            actual_session_id = create_resp.json()["session_id"]

            submit_resp = await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "This is my task 1 essay with more than enough words. " * 20,
                    "task_number": 1,
                },
            )

        assert submit_resp.status_code == 200
        data = submit_resp.json()
        assert data["status"] == "task_submitted"
        assert data["overall_band"] == 7.0
        assert data["task_number"] == 1

        # GOA-058: the per-criterion breakdown must come back on the submit
        # response itself. GET /{id}/result cannot serve the Task 1 card
        # because it 404s until both tasks exist, so without this the UI has
        # no way to show Task 1 feedback while Task 2 is still being written.
        assert "evaluations" in data
        assert {item["criterion"] for item in data["evaluations"]} == {
            "task_response",
            "cohesion",
            "vocabulary",
            "grammar",
        }

        grammar = next(
            item for item in data["evaluations"] if item["criterion"] == "grammar"
        )
        # Inline issues must survive with the field names the Writing service
        # actually emits, or the colour-coded highlighting has no data.
        assert grammar["inline_issues"][0]["issue_type"] == (
            "Incorrect past participle"
        )
        assert grammar["inline_issues"][0]["start_char"] == 0
        assert grammar["inline_issues"][0]["end_char"] == 9

    @pytest.mark.asyncio
    async def test_exm10_writing_submit_task2_final_band(self) -> None:
        """EXM-10: Submit Task 1 + Task 2 → final band = round((T1 + 2*T2)/3 * 2) / 2."""
        question = _writing_question_academic()
        session_id = uuid4()
        task1_band = 6.0
        task2_band = 7.0
        task1_response = _writing_eval_response(session_id, 1, task1_band)
        task2_response = _writing_eval_response(session_id, 2, task2_band)
        writing_client = FakeWritingClient({1: task1_response, 2: task2_response})

        service, _, _ = self._make_service(question, writing_client)
        app = self._make_app(service)
        user_id = str(uuid4())

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            create_resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": user_id,
                    "exam_type": "academic",
                    "skill_area": "writing",
                },
            )
            actual_session_id = create_resp.json()["session_id"]

            await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "Task 1 essay content with sufficient length. " * 20,
                    "task_number": 1,
                },
            )

            submit2_resp = await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "Task 2 essay content discussing the topic in detail. " * 30,
                    "task_number": 2,
                },
            )

        assert submit2_resp.status_code == 200
        data = submit2_resp.json()
        assert data["status"] == "submitted"

        expected_band = round((task1_band + 2 * task2_band) / 3 * 2) / 2
        assert expected_band == 6.5

        result_resp_data = data
        assert result_resp_data["overall_band"] == task2_band

        assert len(writing_client.calls) == 2

    @pytest.mark.asyncio
    async def test_exm11_general_training_no_stimulus(self) -> None:
        """EXM-11: General Training Task 1 (letter) → no stimulusS3Key sent."""
        question = _writing_question_general()
        session_id = uuid4()
        task1_response = _writing_eval_response(session_id, 1, 6.5)
        writing_client = FakeWritingClient({1: task1_response})

        service, _, _ = self._make_service(question, writing_client)
        app = self._make_app(service)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            create_resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": str(uuid4()),
                    "exam_type": "general",
                    "skill_area": "writing",
                },
            )
            actual_session_id = create_resp.json()["session_id"]

            await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "Dear Sir, I am writing to inform you about a problem. " * 20,
                    "task_number": 1,
                },
            )

        assert len(writing_client.calls) == 1
        call = writing_client.calls[0]
        assert call.get("stimulus_s3_key") is None

    # ------------------------------------------------------------------
    # Regression: writing submit returned HTTP 500 on real ingested data
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.parametrize("task_number", [1, 2])
    async def test_writing_submit_succeeds_on_ingested_list_shape(
        self, task_number: int
    ) -> None:
        """
        Regression: submitting a writing task against a question stored in the
        shape real ingestion produces (a LIST of tasks) must return 200.

        _resolve_task_context assumed the task1/task2 dict shape and called
        .get() on the decoded value. A non-empty list is truthy, so it stayed a
        list and .get raised AttributeError — uncaught, so FastAPI returned
        HTTP 500 for BOTH tasks on every real session.

        Parametrized over both tasks because the reported symptom was that
        "submitting either Task 1 or Task 2 returns Internal Server Error".
        """
        question = _writing_question_ingested_list_shape()
        session_id = uuid4()
        writing_client = FakeWritingClient(
            {
                1: _writing_eval_response(session_id, 1, 6.5),
                2: _writing_eval_response(session_id, 2, 7.0),
            }
        )

        service, _, _ = self._make_service(question, writing_client)
        app = self._make_app(service)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            create_resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": str(uuid4()),
                    "exam_type": "academic",
                    "skill_area": "writing",
                },
            )
            actual_session_id = create_resp.json()["session_id"]

            submit_resp = await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "This is a sufficiently long response. " * 20,
                    "task_number": task_number,
                },
            )

        assert submit_resp.status_code == 200, submit_resp.text
        assert submit_resp.json()["task_number"] == task_number

        # The right prompt must reach the Writing service — returning 200 with a
        # None prompt would be a silent regression, not a fix.
        call = writing_client.calls[0]
        expected_prompt = question["questions"][task_number - 1]["prompt"]
        assert call["task_prompt"] == expected_prompt

    @pytest.mark.asyncio
    async def test_writing_full_flow_on_ingested_shape_produces_weighted_band(
        self,
    ) -> None:
        """
        Both tasks submitted against real-shaped data → session scored and the
        combined result carries the 33/67 weighted band.
        """
        question = _writing_question_ingested_list_shape()
        session_id = uuid4()
        writing_client = FakeWritingClient(
            {
                1: _writing_eval_response(session_id, 1, 6.5),
                2: _writing_eval_response(session_id, 2, 7.0),
            }
        )

        service, _, _ = self._make_service(question, writing_client)
        app = self._make_app(service)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            create_resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": str(uuid4()),
                    "exam_type": "academic",
                    "skill_area": "writing",
                },
            )
            actual_session_id = create_resp.json()["session_id"]

            first = await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "Task one response. " * 40,
                    "task_number": 1,
                },
            )
            second = await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "Task two response. " * 60,
                    "task_number": 2,
                },
            )
            result = await client.get(
                f"/sessions/{actual_session_id}/result",
                headers=INTERNAL_HEADERS,
            )

        assert first.status_code == 200, first.text
        assert first.json()["status"] == "task_submitted"
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "submitted"

        assert result.status_code == 200, result.text
        # round((6.5 + 2 * 7.0) / 3 * 2) / 2 == 7.0
        assert result.json()["overall_band"] == 7.0

    @pytest.mark.asyncio
    async def test_academic_task1_sends_no_stimulus_key(self) -> None:
        """
        Image-based evaluation is postponed, so Academic Task 1 must submit
        successfully with no stimulus key rather than being rejected.

        The plumbing stays in place (the Writing service still accepts an
        optional stimulusS3Key), so this asserts the current contract: the key
        is simply absent, and that is not an error.
        """
        question = _writing_question_ingested_list_shape(exam_type="academic")
        session_id = uuid4()
        writing_client = FakeWritingClient(
            {1: _writing_eval_response(session_id, 1, 6.5)}
        )

        service, _, _ = self._make_service(question, writing_client)
        app = self._make_app(service)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            create_resp = await client.post(
                "/sessions",
                headers=INTERNAL_HEADERS,
                json={
                    "user_id": str(uuid4()),
                    "exam_type": "academic",
                    "skill_area": "writing",
                },
            )
            actual_session_id = create_resp.json()["session_id"]

            submit_resp = await client.put(
                f"/sessions/{actual_session_id}/submit",
                headers=INTERNAL_HEADERS,
                json={
                    "answers": {},
                    "essay_text": "The chart shows a clear upward trend. " * 20,
                    "task_number": 1,
                },
            )

        assert submit_resp.status_code == 200, submit_resp.text
        assert writing_client.calls[0].get("stimulus_s3_key") is None


# ---------------------------------------------------------------------------
# TestMetrics — EXM-12
# ---------------------------------------------------------------------------


class TestMetrics:
    """Tests for Prometheus metrics instrumentation."""

    @pytest.mark.asyncio
    async def test_exm12_metrics_after_reading_exam(self) -> None:
        """EXM-12: /metrics shows goa_exam_reading_sessions_total incremented after reading start."""
        question = _reading_question()
        service = SessionService(
            session_repository=FakeSessionRepository(),
            question_repository=FakeQuestionRepository(question),
            result_repository=FakeResultRepository(),
        )

        app = FastAPI()
        app.include_router(reading_router)
        app.mount("/metrics", make_asgi_app())
        app.dependency_overrides[reading_get_session_service] = lambda: service
        user_id = uuid4()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            await client.get(
                f"/exam/reading/start?exam_type=academic&user_id={user_id}",
                headers=INTERNAL_HEADERS,
            )

            metrics_resp = await client.get("/metrics/")

        assert metrics_resp.status_code == 200
        metrics_text = metrics_resp.text
        assert "goa_exam_reading_sessions_total" in metrics_text
