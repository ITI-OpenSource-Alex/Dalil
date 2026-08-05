from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExamHistoryItem(BaseModel):
    """Single entry in a user's exam history."""

    model_config = ConfigDict(populate_by_name=True)

    skill: str
    exam_type: str = Field(alias="examType")
    # GOA-134: nullable. A speaking session where fewer than 3 of 4 criteria
    # completed has no band, and NULL is how that is represented now that
    # exam_results.band_score no longer forces a fabricated 0.0.
    band_score: float | None = Field(default=None, alias="bandScore")
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
