"""Business logic for the exam-history endpoints.

Pure helpers (feedback extraction, weak-area detection) are exposed as
module-level functions so they can be unit-tested without touching the
database. The `HistoryService` glues them onto the repository.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.repositories.history_repository import ExamHistoryRepositoryProtocol
from app.schemas.history import (
    ExamHistoryItem,
    ProgressPoint,
    RecommendationProfile,
)

# Skills we always surface in the recommendation payload, even when the
# user hasn't taken that skill's exam yet (value stays None).
_ALL_SKILLS = ("reading", "listening", "writing", "speaking")


def extract_feedback_summary(agent_responses: Any) -> Optional[str]:
    """Pull the top improvement tip out of an agent_responses payload.

    The payload isn't strictly schema-typed — different skill graders
    (speaking, writing) shape it slightly differently. We look for the
    common cases in order of preference and return the first hit:

    1. Top-level `improvement_tip` (writing-style flat payload).
    2. `dimensions.<criterion>.improvement_tip` (speaking-style nested).
    3. Top-level `overall_feedback` as a last resort.

    Returns None if nothing usable is found so the API contract stays
    honest — an empty string would look like "we tried and it was blank".
    """
    if not isinstance(agent_responses, dict):
        return None

    # Case 1 — flat payload.
    tip = agent_responses.get("improvement_tip")
    if isinstance(tip, str) and tip.strip():
        return tip.strip()

    # Case 2 — nested per-criterion payload (speaking evaluator).
    dimensions = agent_responses.get("dimensions")
    if isinstance(dimensions, dict):
        for detail in dimensions.values():
            if isinstance(detail, dict):
                nested = detail.get("improvement_tip")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()

    # Case 3 — fall back to overall feedback text.
    overall = agent_responses.get("overall_feedback")
    if isinstance(overall, str) and overall.strip():
        return overall.strip()

    return None


def detect_weak_area(section_scores: Any) -> Optional[str]:
    """Return the key with the lowest *absolute* score in `section_scores`.

    Only numeric (int/float, non-bool) values are considered. Ties break
    by insertion order (Python dict ordering) so the result is stable
    across calls with the same payload. Non-dict input, empty dicts, and
    payloads that contain no numeric values all yield None — callers
    surface that as "no weak area detected yet".
    """
    if not isinstance(section_scores, dict) or not section_scores:
        return None

    weakest_key: Optional[str] = None
    weakest_val: Optional[float] = None

    for key, value in section_scores.items():
        # bool is a subclass of int; reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if weakest_val is None or numeric < weakest_val:
            weakest_val = numeric
            weakest_key = str(key)

    return weakest_key


class HistoryService:
    """Coordinates repository fetches with the pure logic above."""

    HISTORY_PAGE_SIZE = 20
    PROGRESS_WINDOW = 10

    def __init__(self, repo: ExamHistoryRepositoryProtocol) -> None:
        self.repo = repo

    async def get_history(
        self, user_id: UUID, page: int
    ) -> list[ExamHistoryItem]:
        page = max(page, 1)
        offset = (page - 1) * self.HISTORY_PAGE_SIZE
        rows = await self.repo.get_history_page(
            user_id, self.HISTORY_PAGE_SIZE, offset
        )
        return [
            ExamHistoryItem(
                skill=row["skill_area"],
                exam_type=row["exam_type"],
                band_score=float(row["band_score"]),
                date=row["graded_at"],
                duration=row.get("duration_seconds"),
                feedback_summary=extract_feedback_summary(
                    row.get("agent_responses")
                ),
            )
            for row in rows
        ]

    async def get_progress(
        self, user_id: UUID
    ) -> dict[str, list[ProgressPoint]]:
        rows = await self.repo.get_last_n_scores_per_skill(
            user_id, self.PROGRESS_WINDOW
        )
        trend: dict[str, list[ProgressPoint]] = {}
        for row in rows:
            skill = row["skill_area"]
            trend.setdefault(skill, []).append(
                ProgressPoint(
                    date=row["graded_at"],
                    band=float(row["band_score"]),
                )
            )
        return trend

    async def get_weak_areas(self, user_id: UUID) -> dict[str, str]:
        rows = await self.repo.get_latest_per_skill(user_id)
        result: dict[str, str] = {}
        for row in rows:
            weakest = detect_weak_area(row.get("section_scores"))
            if weakest is not None:
                result[row["skill_area"]] = weakest
        return result

    async def get_recommendation_profile(
        self, user_id: UUID
    ) -> RecommendationProfile:
        """Never raises — returns a null-filled profile for unknown users."""
        latest_rows = await self.repo.get_latest_per_skill(user_id)
        exam_count = await self.repo.get_exam_count(user_id)
        last_exam_date = await self.repo.get_last_exam_date(user_id)

        band_by_skill: dict[str, float] = {}
        weak: dict[str, str] = {}
        for row in latest_rows:
            skill = row["skill_area"]
            band_by_skill[skill] = float(row["band_score"])
            weakest = detect_weak_area(row.get("section_scores"))
            if weakest is not None:
                weak[skill] = weakest

        return RecommendationProfile(
            reading_band=band_by_skill.get("reading"),
            listening_band=band_by_skill.get("listening"),
            speaking_band=band_by_skill.get("speaking"),
            writing_band=band_by_skill.get("writing"),
            weak_areas=weak if weak else None,
            last_exam_date=last_exam_date,
            exam_count=exam_count,
        )
