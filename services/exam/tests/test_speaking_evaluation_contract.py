"""GOA-134 — the exam side of the holistic band contract.

The speaking service now omits `overall_band` entirely when fewer than 3 of 4
criteria completed. Four links in this service had to change to accept that, and
each one, left alone, breaks the exam speaking flow outright:

  * EvaluationResponse.overall_band was a required `float`   -> ValidationError
  * exam_results.band_score was NOT NULL                     -> insert fails
  * speaking_client's timeout was 30s under a 60s inner budget
  * try_submit ran BEFORE the evaluation, so a failure left the session
    'submitted' with no result and the idempotency guard refused every retry --
    the candidate's exam lost, silently, with a 200 response

The last one is a state-machine bug rather than a contract bug, but the old 15s
holistic deadline made it the normal path rather than an edge case.
"""

import os

os.environ.setdefault("SPEAKING_SERVICE_URL", "http://test-speaking")

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import EvaluationResponse, router as internal_router


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(internal_router)
    return TestClient(app)


def _dimension(band: float = 7.0, timed_out: bool = False) -> dict[str, Any]:
    return {
        "criterion": "fluency",
        "band": band,
        "overall_feedback": "ok",
        "part_notes": {"part1": "ok"},
        "examples": [{"part": 1, "quote": "q", "issue": "i"}],
        "improvement_tip": "tip",
        "timed_out": timed_out,
    }


# --- the wire contract ----------------------------------------------------


def test_evaluation_response_accepts_missing_overall_band() -> None:
    """The single test that proves the two services still speak the same language.

    The speaking service serialises `overall_band` with `omitempty`, so below the
    threshold the KEY IS ABSENT -- not null, not zero. A required float here
    raises and the whole exam speaking flow 500s.
    """
    payload = {
        "status": "completed",
        "partial": True,
        "completed_count": 2,
        "dimensions": {"fluency": _dimension()},
        "overall_feedback": "partial",
    }

    parsed = EvaluationResponse.model_validate(payload)

    assert parsed.overall_band is None
    assert parsed.completed_count == 2


def test_evaluation_response_accepts_present_overall_band() -> None:
    payload = {
        "status": "completed",
        "partial": False,
        "completed_count": 4,
        "overall_band": 7.5,
        "dimensions": {"fluency": _dimension()},
        "overall_feedback": "good",
    }

    parsed = EvaluationResponse.model_validate(payload)

    assert parsed.overall_band == 7.5
    assert parsed.completed_count == 4


def test_evaluation_response_tolerates_absent_completed_count() -> None:
    """A speaking service that has not been redeployed yet must not 500 the exam."""
    payload = {
        "status": "completed",
        "partial": False,
        "overall_band": 7.0,
        "dimensions": {"fluency": _dimension()},
        "overall_feedback": "good",
    }

    parsed = EvaluationResponse.model_validate(payload)

    assert parsed.completed_count is None


# --- persistence ----------------------------------------------------------


@patch("app.api.internal.SessionRepository")
@patch("app.api.internal.TranscriptRepository")
@patch("app.api.internal.SpeakingServiceClient")
@patch("app.api.internal.ResultRepository")
def test_unscored_evaluation_persists_null_band_not_zero(
    mock_result_repo: Any,
    mock_speaking_client: Any,
    mock_transcript_repo: Any,
    mock_session_repo: Any,
) -> None:
    session_id = str(uuid4())

    session = mock_session_repo.return_value
    session.get_by_id = AsyncMock(
        return_value={
            "status": "in_progress",
            "user_id": uuid4(),
            "skill_area": "speaking",
            # Read by record_exam_completion, added on dev after these fixtures
            # were written.
            "exam_type": "academic",
        }
    )
    session.try_submit = AsyncMock(return_value=True)
    session.mark_scored = AsyncMock()
    session.revert_submission = AsyncMock(return_value=True)

    transcripts = mock_transcript_repo.return_value
    transcripts.create_or_update = AsyncMock()
    transcripts.get_all_for_session = AsyncMock(
        return_value=[{"part": 3, "transcript_text": "text"}]
    )

    mock_speaking_client.return_value.evaluate_holistic = AsyncMock(
        return_value={
            "status": "completed",
            "partial": True,
            "completed_count": 2,
            # No overall_band key at all -- the omitempty case.
            "dimensions": {"fluency": _dimension()},
            "overall_feedback": "partial",
        }
    )
    results = mock_result_repo.return_value
    results.create = AsyncMock()

    response = _client().post(
        f"/internal/sessions/{session_id}/speaking/transcripts",
        headers=INTERNAL_HEADERS,
        json={
            "part": 3,
            "transcript_text": "text",
            "duration_s": 120,
            "question_text": "q",
        },
    )

    assert response.status_code == 200
    band = results.create.call_args[1]["band_score"]
    assert band is None
    assert band != 0.0, "0.0 is a band the model never produced (BUG-055)"
    session.revert_submission.assert_not_awaited()


# --- the orphaned-session bug --------------------------------------------


@patch("app.api.internal.SessionRepository")
@patch("app.api.internal.TranscriptRepository")
@patch("app.api.internal.SpeakingServiceClient")
@patch("app.api.internal.ResultRepository")
def test_failed_evaluation_does_not_orphan_session(
    mock_result_repo: Any,
    mock_speaking_client: Any,
    mock_transcript_repo: Any,
    mock_session_repo: Any,
) -> None:
    """try_submit runs before the evaluation. If the evaluation dies, the session
    must not be left 'submitted' with no result -- the guard at the top of the
    endpoint would then refuse every retry and the exam is unrecoverable."""
    session_id = str(uuid4())

    session = mock_session_repo.return_value
    session.get_by_id = AsyncMock(
        return_value={
            "status": "in_progress",
            "user_id": uuid4(),
            "skill_area": "speaking",
            # Read by record_exam_completion, added on dev after these fixtures
            # were written.
            "exam_type": "academic",
        }
    )
    session.try_submit = AsyncMock(return_value=True)
    session.mark_scored = AsyncMock()
    session.revert_submission = AsyncMock(return_value=True)

    transcripts = mock_transcript_repo.return_value
    transcripts.create_or_update = AsyncMock()
    transcripts.get_all_for_session = AsyncMock(
        return_value=[{"part": 3, "transcript_text": "text"}]
    )

    mock_speaking_client.return_value.evaluate_holistic = AsyncMock(
        side_effect=httpx.ReadTimeout("speaking service did not answer")
    )
    mock_result_repo.return_value.create = AsyncMock()

    with pytest.raises(httpx.ReadTimeout):
        _client().post(
            f"/internal/sessions/{session_id}/speaking/transcripts",
            headers=INTERNAL_HEADERS,
            json={
                "part": 3,
                "transcript_text": "text",
                "duration_s": 120,
                "question_text": "q",
            },
        )

    session.revert_submission.assert_awaited_once()
    session.mark_scored.assert_not_awaited()
    mock_result_repo.return_value.create.assert_not_awaited()


@patch("app.api.internal.SessionRepository")
@patch("app.api.internal.TranscriptRepository")
@patch("app.api.internal.SpeakingServiceClient")
@patch("app.api.internal.ResultRepository")
def test_persist_failure_also_reverts(
    mock_result_repo: Any,
    mock_speaking_client: Any,
    mock_transcript_repo: Any,
    mock_session_repo: Any,
) -> None:
    """The revert must cover the whole critical section, not just the HTTP call.
    A database failure after a successful evaluation orphans the session too."""
    session_id = str(uuid4())

    session = mock_session_repo.return_value
    session.get_by_id = AsyncMock(
        return_value={
            "status": "in_progress",
            "user_id": uuid4(),
            "skill_area": "speaking",
            # Read by record_exam_completion, added on dev after these fixtures
            # were written.
            "exam_type": "academic",
        }
    )
    session.try_submit = AsyncMock(return_value=True)
    session.mark_scored = AsyncMock()
    session.revert_submission = AsyncMock(return_value=True)

    transcripts = mock_transcript_repo.return_value
    transcripts.create_or_update = AsyncMock()
    transcripts.get_all_for_session = AsyncMock(
        return_value=[{"part": 3, "transcript_text": "text"}]
    )

    mock_speaking_client.return_value.evaluate_holistic = AsyncMock(
        return_value={
            "status": "completed",
            "partial": False,
            "completed_count": 4,
            "overall_band": 7.0,
            "dimensions": {"fluency": _dimension()},
            "overall_feedback": "good",
        }
    )
    mock_result_repo.return_value.create = AsyncMock(side_effect=RuntimeError("db down"))

    with pytest.raises(RuntimeError):
        _client().post(
            f"/internal/sessions/{session_id}/speaking/transcripts",
            headers=INTERNAL_HEADERS,
            json={
                "part": 3,
                "transcript_text": "text",
                "duration_s": 120,
                "question_text": "q",
            },
        )

    session.revert_submission.assert_awaited_once()
    session.mark_scored.assert_not_awaited()


@patch("app.api.internal.SessionRepository")
@patch("app.api.internal.TranscriptRepository")
def test_resubmit_guard_still_idempotent(
    mock_transcript_repo: Any,
    mock_session_repo: Any,
) -> None:
    """Guards against 'fixing' the orphan bug by deleting the guard, which would
    trade a lost exam for a double-graded one."""
    session_id = str(uuid4())

    session = mock_session_repo.return_value
    session.get_by_id = AsyncMock(
        return_value={
            "status": "scored",
            "user_id": uuid4(),
            "skill_area": "speaking",
            "exam_type": "academic",
        }
    )
    transcripts = mock_transcript_repo.return_value
    transcripts.create_or_update = AsyncMock()

    response = _client().post(
        f"/internal/sessions/{session_id}/speaking/transcripts",
        headers=INTERNAL_HEADERS,
        json={
            "part": 3,
            "transcript_text": "text",
            "duration_s": 120,
            "question_text": "q",
        },
    )

    assert response.status_code == 200
    assert response.json() == {}
    transcripts.create_or_update.assert_not_awaited()


# --- the timeout invariant ------------------------------------------------


def test_speaking_client_timeout_exceeds_speaking_swarm_budget() -> None:
    """The outer HTTP timeout must be strictly greater than the inner swarm budget.

    Otherwise the exam service aborts an evaluation that was going to succeed,
    and the session is reverted for no reason. Both values come from config, so
    this fails if either is tuned in isolation.

    The inner budget is `swarmEvaluationTimeout` in
    services/speaking/internal/speaking/client.go, read from source rather than
    duplicated as a literal here -- a duplicated constant is how the two paths
    drifted in the first place.
    """
    import re
    from pathlib import Path

    from app.core.config import settings

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "services" / "speaking" / "internal" / "speaking" / "holistic_handler.go"
        if candidate.exists():
            source = candidate.read_text(encoding="utf-8")
            break
    else:
        pytest.skip("speaking service source not reachable from this checkout")

    # holisticSwarmTimeout, not swarmEvaluationTimeout. This test read the
    # streaming path's constant while the exam client calls the HOLISTIC
    # endpoint, so it was comparing the client timeout against a budget that
    # bounds a different request. It passed (75 > 60) while the real
    # relationship had inverted (75 < 120) -- a guard watching the wrong number
    # is worse than no guard, because it reports safety it never checked.
    match = re.search(r"holisticSwarmTimeout\s*=\s*(\d+)\s*\*\s*time\.Second", source)
    assert match, "could not read holisticSwarmTimeout from holistic_handler.go"
    inner_budget_s = float(match.group(1))

    assert settings.speaking_evaluation_timeout_s > inner_budget_s, (
        f"exam timeout {settings.speaking_evaluation_timeout_s}s must exceed the "
        f"speaking swarm budget {inner_budget_s}s, or a succeeding evaluation is "
        f"aborted by the caller"
    )


def test_speaking_client_uses_configured_timeout() -> None:
    from app.core.config import settings
    from app.services.speaking_client import SpeakingServiceClient

    client = SpeakingServiceClient("http://speaking", "key")

    assert client.timeout_s == settings.speaking_evaluation_timeout_s
    assert client.timeout_s != 30.0, "the hardcoded 30.0 is the value this ticket removed"


# --- observability must tolerate an unscored exam --------------------------


def test_record_exam_completion_accepts_a_null_band() -> None:
    """A merge-interaction bug, caught when dev's GOA-066 observability met
    GOA-134's nullable band.

    `record_exam_completion` observed band_score into a Prometheus histogram
    unconditionally. A partial speaking evaluation produces no band, and
    `float += None` inside prometheus_client crashed the endpoint -- after the
    result row had already been written, so the surrounding try/except reverted
    a submission that had in fact succeeded.

    Neither change was wrong on its own and they did not conflict textually.
    """
    from app.core.exam_observability import record_exam_completion

    record_exam_completion(
        session_id=uuid4(),
        user_id=uuid4(),
        skill_area="speaking",
        exam_type="academic",
        band_score=None,
        duration_s=120,
        question_bank_ref=None,
    )


def test_unscored_exam_is_counted_but_not_observed_as_zero() -> None:
    """0.0 in the histogram would be a band no candidate received, dragging every
    reported percentile down -- BUG-055 in a dashboard."""
    from app.core.metrics import (
        goa_exam_score_distribution,
        goa_exam_unscored_total,
    )
    from app.core.exam_observability import record_exam_completion

    labels = {"skill_area": "speaking", "exam_type": "general"}
    before_unscored = goa_exam_unscored_total.labels(**labels)._value.get()
    before_observed = goa_exam_score_distribution.labels(**labels)._sum.get()

    record_exam_completion(
        session_id=uuid4(),
        user_id=uuid4(),
        skill_area="speaking",
        exam_type="general",
        band_score=None,
        duration_s=90,
        question_bank_ref=None,
    )

    assert goa_exam_unscored_total.labels(**labels)._value.get() == before_unscored + 1
    assert goa_exam_score_distribution.labels(**labels)._sum.get() == before_observed
