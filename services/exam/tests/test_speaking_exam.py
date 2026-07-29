import os

os.environ["SPEAKING_SERVICE_URL"] = "http://test-speaking"

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import router as internal_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(internal_router)
    return TestClient(app)


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


def test_part_2_duration_rejection() -> None:
    client = _client()
    session_id = str(uuid4())

    response = client.post(
        f"/internal/sessions/{session_id}/speaking/transcripts",
        headers=INTERNAL_HEADERS,
        json={
            "part": 2,
            "transcript_text": "short response",
            "duration_s": 50,
            "question_text": "topic",
        },
    )

    assert response.status_code == 400


@patch("app.api.internal.SessionRepository")
@patch("app.api.internal.TranscriptRepository")
def test_no_feedback_leaks_mid_exam(
    mock_transcript_repo: Any, mock_session_repo: Any
) -> None:
    # Setup mocks
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

    client = _client()
    session_id = str(uuid4())

    # Test Part 1
    response1 = client.post(
        f"/internal/sessions/{session_id}/speaking/transcripts",
        headers=INTERNAL_HEADERS,
        json={
            "part": 1,
            "transcript_text": "test part 1",
            "duration_s": 60,
            "question_text": "topic 1",
        },
    )
    assert response1.status_code == 200
    assert response1.json() == {}

    # Test Part 2
    response2 = client.post(
        f"/internal/sessions/{session_id}/speaking/transcripts",
        headers=INTERNAL_HEADERS,
        json={
            "part": 2,
            "transcript_text": "test part 2",
            "duration_s": 120,
            "question_text": "topic 2",
        },
    )
    assert response2.status_code == 200
    assert response2.json() == {}


@patch("app.api.internal.SessionRepository")
@patch("app.api.internal.TranscriptRepository")
@patch("app.api.internal.SpeakingServiceClient")
@patch("app.api.internal.ResultRepository")
def test_concatenated_string_payload_and_agent_response(
    mock_result_repo: Any,
    mock_speaking_client: Any,
    mock_transcript_repo: Any,
    mock_session_repo: Any,
) -> None:
    session_id_uuid = uuid4()
    session_id = str(session_id_uuid)

    mock_session_instance = mock_session_repo.return_value
    mock_session_instance.get_by_id = AsyncMock(
        return_value={
            "status": "in_progress",
            "user_id": uuid4(),
            "skill_area": "speaking",
        }
    )
    mock_session_instance.submit = AsyncMock()
    mock_session_instance.mark_scored = AsyncMock()
    mock_session_instance.try_submit = AsyncMock(return_value=True)

    mock_transcript_instance = mock_transcript_repo.return_value
    mock_transcript_instance.create_or_update = AsyncMock()
    mock_transcript_instance.get_all_for_session = AsyncMock(
        return_value=[
            {"part": 1, "transcript_text": "I like apples."},
            {"part": 2, "transcript_text": "I went to the store."},
            {"part": 3, "transcript_text": "Fruits are healthy."},
        ]
    )

    mock_speaking_client_instance = mock_speaking_client.return_value
    eval_result = {
        "status": "completed",
        "partial": False,
        "overall_band": 7.5,
        "dimensions": {
            "fluency": {
                "criterion": "fluency",
                "band": 7.0,
                "overall_feedback": "Good",
                "part_notes": {"Part 1": "Good"},
                "examples": [{"part": 1, "quote": "example 1", "issue": "issue 1"}],
                "improvement_tip": "tip",
                "timed_out": False,
            },
            "lexical": {
                "criterion": "lexical",
                "band": 8.0,
                "overall_feedback": "Good",
                "part_notes": {"Part 1": "Good"},
                "examples": [{"part": 1, "quote": "example 1", "issue": "issue 1"}],
                "improvement_tip": "tip",
                "timed_out": False,
            },
        },
        "overall_feedback": "Good job",
    }
    mock_speaking_client_instance.evaluate_holistic = AsyncMock(
        return_value=eval_result
    )

    mock_result_instance = mock_result_repo.return_value
    mock_result_instance.create = AsyncMock()

    client = _client()

    response = client.post(
        f"/internal/sessions/{session_id}/speaking/transcripts",
        headers=INTERNAL_HEADERS,
        json={
            "part": 3,
            "transcript_text": "Fruits are healthy.",
            "duration_s": 120,
            "question_text": "topic 3",
        },
    )

    assert response.status_code == 200

    # Verify concatenation format
    mock_speaking_client_instance.evaluate_holistic.assert_called_once()
    called_payload = mock_speaking_client_instance.evaluate_holistic.call_args[0][1]
    expected_concatenated = "Part 1:\nI like apples.\nPart 2:\nI went to the store.\nPart 3:\nFruits are healthy."
    assert called_payload["concatenated_transcript"] == expected_concatenated

    # Verify agent response extraction
    mock_result_instance.create.assert_called_once()
    create_kwargs = mock_result_instance.create.call_args[1]
    assert create_kwargs["band_score"] == 7.5
    assert create_kwargs["section_scores"] == {"fluency": 7.0, "lexical": 8.0}
    assert create_kwargs["agent_responses"]["status"] == "completed"
    assert create_kwargs["agent_responses"]["dimensions"]["fluency"]["band"] == 7.0


@pytest.mark.asyncio
async def test_speaking_flow_integration() -> None:
    from app.core.database import db
    from app.main import app
    import httpx
    from uuid import UUID

    try:
        await db.connect()
    except Exception:
        pytest.skip("Database not available for integration test")

    session_id = str(uuid4())
    user_id = str(uuid4())
    question_id = str(uuid4())
    book_ref = f"test_book_{question_id}"

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO questions (id, book_ref, test_number, exam_type, skill_area, passage_text, audio_s3_key, answer_key, questions)
            VALUES ($1, $2, 1, 'academic', 'speaking', '', '', '{}', '[]')
            """,
            UUID(question_id),
            book_ref,
        )
        await conn.execute(
            """
            INSERT INTO exam_sessions (id, user_id, question_id, exam_type, skill_area, status, started_at, time_limit_seconds)
            VALUES ($1, $2, $3, 'academic', 'speaking', 'in_progress', NOW(), 900)
            """,
            UUID(session_id),
            UUID(user_id),
            UUID(question_id),
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch("app.api.internal.SpeakingServiceClient") as mock_speaking_client:
            mock_speaking_client_instance = mock_speaking_client.return_value
            mock_speaking_client_instance.evaluate_holistic = AsyncMock(
                return_value={
                    "status": "completed",
                    "partial": False,
                    "overall_band": 8.0,
                    "dimensions": {
                        "fluency": {
                            "criterion": "fluency",
                            "band": 8.0,
                            "overall_feedback": "Great",
                            "part_notes": {"Part 1": "Good"},
                            "examples": [{"part": 1, "quote": "test", "issue": "test"}],
                            "improvement_tip": "tip",
                            "timed_out": False,
                        },
                        "lexical": {
                            "criterion": "lexical",
                            "band": 8.0,
                            "overall_feedback": "Great",
                            "part_notes": {"Part 1": "Good"},
                            "examples": [{"part": 1, "quote": "test", "issue": "test"}],
                            "improvement_tip": "tip",
                            "timed_out": False,
                        },
                    },
                    "overall_feedback": "Great",
                }
            )

            res1 = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=INTERNAL_HEADERS,
                json={
                    "part": 1,
                    "transcript_text": "t1",
                    "duration_s": 60,
                    "question_text": "q1",
                },
            )
            assert res1.status_code == 200

            res2 = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=INTERNAL_HEADERS,
                json={
                    "part": 2,
                    "transcript_text": "t2",
                    "duration_s": 120,
                    "question_text": "q2",
                },
            )
            assert res2.status_code == 200

            res3 = await client.post(
                f"/internal/sessions/{session_id}/speaking/transcripts",
                headers=INTERNAL_HEADERS,
                json={
                    "part": 3,
                    "transcript_text": "t3",
                    "duration_s": 120,
                    "question_text": "q3",
                },
            )
            assert res3.status_code == 200

            async with db.pool.acquire() as conn:
                status = await conn.fetchval(
                    "SELECT status FROM exam_sessions WHERE id = $1", UUID(session_id)
                )
                assert status == "scored"

    async with db.pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM exam_results WHERE session_id = $1", UUID(session_id)
        )
        await conn.execute(
            "DELETE FROM exam_speaking_transcripts WHERE session_id = $1",
            UUID(session_id),
        )
        await conn.execute("DELETE FROM exam_sessions WHERE id = $1", UUID(session_id))
        await conn.execute("DELETE FROM questions WHERE id = $1", UUID(question_id))
