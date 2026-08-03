"""GET endpoints for exam history, progress, weak-area detection, and
the recommendation-service profile (internal).

All handlers increment `goa_exam_history_requests_total` labelled with
the logical endpoint name so Grafana can slice traffic per-view.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.database import db
from app.core.metrics import goa_exam_history_requests_total
from app.core.security import validate_internal_api_key
from app.repositories.history_repository import ExamHistoryRepository
from app.schemas.history import (
    ExamHistoryItem,
    ProgressPoint,
    RecommendationProfile,
)
from app.services.history_service import HistoryService


router = APIRouter(tags=["history"])


def get_history_service() -> HistoryService:
    """Default DI wiring: build a service on top of the live pg pool."""
    return HistoryService(ExamHistoryRepository(db.pool))


# ---------------------------------------------------------------------------
# Public (user-facing) endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/users/{user_id}/exam-history",
    response_model=list[ExamHistoryItem],
)
async def list_exam_history(
    user_id: UUID,
    page: int = Query(1, ge=1),
    service: HistoryService = Depends(get_history_service),
) -> list[ExamHistoryItem]:
    """Paginated exam history for a user, 20 rows per page.

    `feedback_summary` is pre-extracted from the stored `agent_responses`
    so clients don't have to display (or download) the full evaluation.
    """
    goa_exam_history_requests_total.labels(endpoint="exam_history").inc()
    return await service.get_history(user_id, page)


@router.get(
    "/users/{user_id}/progress",
    response_model=dict[str, list[ProgressPoint]],
)
async def get_progress(
    user_id: UUID,
    service: HistoryService = Depends(get_history_service),
) -> dict[str, list[ProgressPoint]]:
    """Return the last 10 scores per skill, ordered oldest → newest.

    Backed by a single window-function query — safe to hit on
    dashboard loads without fanning out per-skill.
    """
    goa_exam_history_requests_total.labels(endpoint="progress").inc()
    return await service.get_progress(user_id)


@router.get(
    "/users/{user_id}/weak-areas",
    response_model=dict[str, str],
)
async def get_weak_areas(
    user_id: UUID,
    service: HistoryService = Depends(get_history_service),
) -> dict[str, str]:
    """For each skill, name the sub-section with the lowest score in the
    user's most recent exam of that skill."""
    goa_exam_history_requests_total.labels(endpoint="weak_areas").inc()
    return await service.get_weak_areas(user_id)


# ---------------------------------------------------------------------------
# Internal endpoint (consumed by the recommendation service)
# ---------------------------------------------------------------------------

@router.get(
    "/internal/users/{user_id}/profile-for-recommendation",
    response_model=RecommendationProfile,
    dependencies=[Depends(validate_internal_api_key)],
)
async def get_recommendation_profile(
    user_id: UUID,
    service: HistoryService = Depends(get_history_service),
) -> RecommendationProfile:
    """Aggregated profile for the recommender.

    Contract: this MUST return 200 even for users we've never seen — the
    recommender treats "no data" as a legitimate cold-start signal, so a
    404 here would trigger spurious error alerts upstream.
    """
    goa_exam_history_requests_total.labels(
        endpoint="profile_for_recommendation"
    ).inc()
    return await service.get_recommendation_profile(user_id)
