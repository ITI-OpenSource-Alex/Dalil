"""
Contract tests between the Exam service and the Writing service.

These exist because the two services disagreed about the shape of a criterion
evaluation and nothing caught it: the Exam service's client modelled
`highlighted_issues: [{issue, start, end}]`, a shape the Writing service has
never emitted — it returns `inline_issues: [{issue_type, start_char, end_char}]`
(services/writing/app/schemas.py). Validating a genuine response therefore
raised ValidationError, which `evaluate_exam_essay` does not catch, so every
writing task submit failed as an unhandled 500.

The existing suite missed it because its own fixture used the client's
(incorrect) spelling rather than the Writing service's real payload. The tests
below are pinned to the *producer's* schema on purpose.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.writing_client import (
    ExamTaskEvaluationResponse,
    WritingClient,
    WritingServiceError,
)


def _writing_service_payload(**overrides: Any) -> dict[str, Any]:
    """A response exactly as services/writing/app/schemas.py serialises it."""
    payload: dict[str, Any] = {
        "essay_id": 1,
        "exam_session_id": str(uuid4()),
        "task_number": 1,
        "overall_band": 7.0,
        "from_cache": False,
        "evaluations": [
            {
                "criterion": "grammar",
                "band_score": 6.5,
                "feedback": "Some tense inconsistencies.",
                "improvement_tip": "Revise past participles.",
                "word_count": 162,
                "inline_issues": [
                    {
                        "text": "have went",
                        "issue_type": "Incorrect past participle",
                        "suggestion": "have gone",
                        "start_char": 10,
                        "end_char": 19,
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


class TestEvaluationContract:
    def test_parses_a_real_writing_service_response(self) -> None:
        parsed = ExamTaskEvaluationResponse.model_validate(
            _writing_service_payload()
        )

        assert parsed.overall_band == 7.0
        issue = parsed.evaluations[0].inline_issues[0]
        assert issue.issue_type == "Incorrect past participle"
        assert issue.start_char == 10
        assert issue.end_char == 19

    def test_carries_improvement_tip_and_word_count(self) -> None:
        parsed = ExamTaskEvaluationResponse.model_validate(
            _writing_service_payload()
        )

        assert parsed.evaluations[0].improvement_tip == (
            "Revise past participles."
        )
        assert parsed.evaluations[0].word_count == 162

    def test_serialises_on_the_producers_field_names(self) -> None:
        """
        The frontend reads these keys straight off the submit response, so the
        dumped names must match the Writing service's, not the old aliases.
        """
        parsed = ExamTaskEvaluationResponse.model_validate(
            _writing_service_payload()
        )
        dumped = parsed.model_dump()["evaluations"][0]

        assert "inline_issues" in dumped
        assert "highlighted_issues" not in dumped
        assert set(dumped["inline_issues"][0]) == {
            "text",
            "issue_type",
            "suggestion",
            "start_char",
            "end_char",
        }

    def test_still_accepts_the_legacy_spelling(self) -> None:
        """Backwards compatibility: nothing that used to validate should stop."""
        legacy = _writing_service_payload(
            evaluations=[
                {
                    "criterion": "cohesion",
                    "band_score": 6.0,
                    "feedback": "Repetitive linking.",
                    "highlighted_issues": [
                        {
                            "text": "Moreover",
                            "issue": "Overused connective",
                            "suggestion": "In addition",
                            "start": 4,
                            "end": 12,
                        }
                    ],
                }
            ]
        )

        parsed = ExamTaskEvaluationResponse.model_validate(legacy)
        issue = parsed.evaluations[0].inline_issues[0]
        assert issue.issue_type == "Overused connective"
        assert (issue.start_char, issue.end_char) == (4, 12)

    def test_a_criterion_with_no_issues_is_valid(self) -> None:
        """
        A criterion the model found nothing to underline must not fail the whole
        submit — `inline_issues` defaults to empty rather than being required.
        """
        payload = _writing_service_payload(
            evaluations=[
                {
                    "criterion": "task_response",
                    "band_score": 7.0,
                    "feedback": "Covers both views.",
                }
            ]
        )

        parsed = ExamTaskEvaluationResponse.model_validate(payload)
        assert parsed.evaluations[0].inline_issues == []

    def test_a_genuinely_malformed_payload_still_fails(self) -> None:
        """The aliases must not have made the model accept anything at all."""
        with pytest.raises(ValidationError):
            ExamTaskEvaluationResponse.model_validate(
                _writing_service_payload(
                    evaluations=[{"criterion": "not_a_criterion"}]
                )
            )


class _StubResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _StubAsyncClient:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def __call__(self, *args: Any, **kwargs: Any) -> "_StubAsyncClient":
        return self

    async def __aenter__(self) -> "_StubAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> _StubResponse:
        return _StubResponse(self._payload)


class TestUnreadableResponseHandling:
    @pytest.mark.asyncio
    async def test_unreadable_2xx_becomes_a_writing_service_error(self) -> None:
        """
        A 200 whose body the client cannot parse must surface as
        WritingServiceError so the caller turns it into a 502 (an upstream
        failure). Letting a raw ValidationError escape produced an unhandled
        500 that blamed the exam service for the Writing service's payload.
        """
        client = WritingClient(base_url="http://writing:8000")
        stub = _StubAsyncClient({"nonsense": True})

        with patch("app.services.writing_client.httpx.AsyncClient", stub):
            with pytest.raises(WritingServiceError) as excinfo:
                await client.evaluate_exam_essay(
                    user_id=str(uuid4()),
                    essay_text="An essay.",
                    exam_type="academic",
                    exam_session_id=uuid4(),
                    task_number=1,
                )

        assert "unreadable evaluation" in str(excinfo.value)
