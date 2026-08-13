"""Unit tests for the GOA-066 observability helpers.

Covers ``app.core.exam_observability`` in isolation: the score-distribution
histogram, the question-bank-size gauge refresh (including the zero-fill that
keeps a drained bank from reporting a stale count), and the structured
``exam_completed`` log with its fixed seven-field set.
"""

from __future__ import annotations

from uuid import uuid4

from prometheus_client import REGISTRY
from structlog.testing import capture_logs

from app.core import exam_observability
from app.core.exam_observability import (
    record_exam_completion,
    refresh_question_bank_size,
)


def _score_bucket(skill_area: str, exam_type: str, le: str) -> float | None:
    return REGISTRY.get_sample_value(
        "goa_exam_score_distribution_bucket",
        {"skill_area": skill_area, "exam_type": exam_type, "le": le},
    )


def _score_count(skill_area: str, exam_type: str) -> float | None:
    return REGISTRY.get_sample_value(
        "goa_exam_score_distribution_count",
        {"skill_area": skill_area, "exam_type": exam_type},
    )


def _gauge(skill_area: str, exam_type: str) -> float | None:
    return REGISTRY.get_sample_value(
        "goa_question_bank_size",
        {"skill_area": skill_area, "exam_type": exam_type},
    )


def test_record_exam_completion_observes_band_into_the_histogram() -> None:
    # Distinct labels so this test never collides with another's samples.
    skill_area, exam_type = "reading", "academic"
    before = _score_count(skill_area, exam_type) or 0.0

    record_exam_completion(
        session_id=uuid4(),
        user_id=uuid4(),
        skill_area=skill_area,
        exam_type=exam_type,
        band_score=6.5,
        duration_s=123.0,
        question_bank_ref="IELTS-18",
    )

    assert _score_count(skill_area, exam_type) == before + 1
    # 6.5 falls in the (6.0, 7.0] bucket: it counts toward le=7 and above,
    # not le=6. The +Inf bucket must always move with the count.
    assert _score_bucket(skill_area, exam_type, "7.0") >= 1.0
    assert _score_bucket(skill_area, exam_type, "+Inf") == before + 1


def test_record_exam_completion_emits_exactly_the_seven_ac_fields() -> None:
    session_id = uuid4()
    user_id = uuid4()

    with capture_logs() as logs:
        record_exam_completion(
            session_id=session_id,
            user_id=user_id,
            skill_area="listening",
            exam_type="general",
            band_score=7.0,
            duration_s=456.0,
            question_bank_ref="IELTS-17",
        )

    completion = [log for log in logs if log["event"] == "exam_completed"]
    assert len(completion) == 1
    entry = completion[0]

    # UUIDs are stringified so the JSON renderer never chokes on a UUID object.
    assert entry["session_id"] == str(session_id)
    assert entry["user_id"] == str(user_id)
    assert entry["skill_area"] == "listening"
    assert entry["exam_type"] == "general"
    assert entry["band_score"] == 7.0
    assert entry["duration_s"] == 456.0
    assert entry["question_bank_ref"] == "IELTS-17"

    # Exactly the AC field set (plus structlog's own event/log_level keys).
    payload_keys = set(entry) - {"event", "log_level"}
    assert payload_keys == {
        "session_id",
        "user_id",
        "skill_area",
        "exam_type",
        "band_score",
        "duration_s",
        "question_bank_ref",
    }


def test_record_exam_completion_logs_none_ref_without_raising() -> None:
    # A missing question bank reference is an intentional, non-fatal degradation
    # (the result is already scored by the time the log is emitted).
    with capture_logs() as logs:
        record_exam_completion(
            session_id=uuid4(),
            user_id=uuid4(),
            skill_area="speaking",
            exam_type="academic",
            band_score=8.0,
            duration_s=None,
            question_bank_ref=None,
        )

    entry = next(log for log in logs if log["event"] == "exam_completed")
    assert entry["question_bank_ref"] is None
    assert entry["duration_s"] is None


def test_refresh_question_bank_size_sets_gauge_from_rows() -> None:
    refresh_question_bank_size(
        [
            {"skill_area": "reading", "exam_type": "academic", "count": 12},
            {"skill_area": "listening", "exam_type": "general", "count": 3},
        ]
    )

    assert _gauge("reading", "academic") == 12.0
    assert _gauge("listening", "general") == 3.0


def test_refresh_zeroes_the_full_grid_before_applying_counts() -> None:
    # Every known (skill_area, exam_type) pair is present after a refresh, even
    # those with no rows in the incoming stats.
    refresh_question_bank_size(
        [{"skill_area": "writing", "exam_type": "academic", "count": 4}]
    )

    for skill_area in exam_observability._SKILL_AREAS:
        for exam_type in exam_observability._EXAM_TYPES:
            assert _gauge(skill_area, exam_type) is not None

    assert _gauge("writing", "academic") == 4.0
    # A pair absent from the stats reads zero, not None.
    assert _gauge("speaking", "general") == 0.0


def test_refresh_drops_stale_count_when_a_pair_empties() -> None:
    # The regression this zero-fill exists to prevent: a pair drops to zero rows,
    # so GROUP BY emits no row for it, and without the pre-zero pass the gauge
    # would keep its previous non-zero reading and hide the drop.
    refresh_question_bank_size(
        [{"skill_area": "reading", "exam_type": "general", "count": 9}]
    )
    assert _gauge("reading", "general") == 9.0

    refresh_question_bank_size([])  # bank drained
    assert _gauge("reading", "general") == 0.0
