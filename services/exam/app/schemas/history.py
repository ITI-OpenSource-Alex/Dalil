from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class ExamHistoryItem(BaseModel):
    """Single entry in a user's exam history."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: UUID = Field(alias="sessionId")
    skill: str
    exam_type: str = Field(alias="examType")
    band_score: float = Field(alias="bandScore")
    date: datetime
    duration: Optional[int] = None
    feedback_summary: Optional[str] = None


class ProgressPoint(BaseModel):
    """One data point in a skill's band-score trend."""

    date: datetime
    band: float


class RecommendationProfile(BaseModel):
    """Aggregated user profile consumed by the recommendation service."""

    reading_band: Optional[float] = None
    listening_band: Optional[float] = None
    speaking_band: Optional[float] = None
    writing_band: Optional[float] = None
    weak_areas: Optional[dict[str, str]] = None
    last_exam_date: Optional[datetime] = None
    exam_count: int = 0
