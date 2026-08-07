"""Shared observability helpers for exam completions (GOA-066).

Every graded exam funnels through :func:`record_exam_completion` so the
score-distribution histogram and the structured completion log stay in lockstep
and carry the same field set no matter which skill area produced the result.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from app.core.metrics import goa_exam_score_distribution, goa_question_bank_size

logger = structlog.get_logger("exam_service.completion")

# The canonical (skill_area, exam_type) grid the question bank is reported over.
# Mirrors the zero-fill in the /question-bank/stats endpoint (BUG-020): an empty
# bank must read zero, not "absent".
_SKILL_AREAS = ("reading", "listening", "writing", "speaking")
_EXAM_TYPES = ("academic", "general")


def refresh_question_bank_size(stats: list[dict[str, Any]]) -> None:
    """Set the question-bank-size gauge from ``get_question_bank_stats`` rows.

    Each row is ``{exam_type, skill_area, count}``. The gauge is authoritative
    per (skill_area, exam_type) label pair, so ``.set`` (not ``.inc``) is
    correct — a refresh fully replaces the previous reading.

    ``get_question_bank_stats`` runs ``GROUP BY exam_type, skill_area`` over the
    ``questions`` table, so a pair with no rows produces no row at all. Without
    the pre-zero pass below, a pair that drops from N to 0 would keep its stale
    reading of N and hide the drop — the exact condition this gauge exists to
    surface. Zero the known grid first, then overwrite with the live counts.
    """

    for skill_area in _SKILL_AREAS:
        for exam_type in _EXAM_TYPES:
            goa_question_bank_size.labels(
                skill_area=skill_area,
                exam_type=exam_type,
            ).set(0)

    for row in stats:
        goa_question_bank_size.labels(
            skill_area=row["skill_area"],
            exam_type=row["exam_type"],
        ).set(row["count"])


def record_exam_completion(
    *,
    session_id: UUID | str,
    user_id: UUID | str,
    skill_area: str,
    exam_type: str,
    band_score: float,
    duration_s: float | None,
    question_bank_ref: str | None,
) -> None:
    """Observe the band score and emit the structured exam-completion log.

    The field set is fixed by the GOA-066 acceptance criteria:
    ``session_id, user_id, skill_area, exam_type, band_score, duration_s,
    question_bank_ref``. Correlation ID is attached automatically by the
    structlog ``inject_correlation_id`` processor already configured for the
    service.
    """

    goa_exam_score_distribution.labels(
        skill_area=skill_area,
        exam_type=exam_type,
    ).observe(band_score)

    logger.info(
        "exam_completed",
        session_id=str(session_id),
        user_id=str(user_id),
        skill_area=skill_area,
        exam_type=exam_type,
        band_score=band_score,
        duration_s=duration_s,
        question_bank_ref=question_bank_ref,
    )
