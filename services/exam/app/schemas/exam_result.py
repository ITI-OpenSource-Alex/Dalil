from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import SkillArea


class ExamResultResponse(BaseModel):
    """Response payload for a scored IELTS exam result."""

    id: UUID
    session_id: UUID
    user_id: UUID
    skill_area: SkillArea
    raw_score: int
    # GOA-134: nullable. A speaking session where fewer than 3 of 4 criteria
    # completed has no band, and NULL is how that is represented now that
    # exam_results.band_score no longer forces a fabricated 0.0.
    band_score: float | None = None
    section_scores: dict[str, Any]
    graded_at: datetime
    answer_key: dict[str, Any]
