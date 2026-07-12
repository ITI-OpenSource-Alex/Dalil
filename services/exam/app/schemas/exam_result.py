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
    band_score: float
    section_scores: dict[str, Any]
    graded_at: datetime
    answer_key: dict[str, Any]
