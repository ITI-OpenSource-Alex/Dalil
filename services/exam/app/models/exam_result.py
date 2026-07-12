from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass(slots=True)
class ExamResult:
    id: UUID
    session_id: UUID
    user_id: UUID
    skill_area: str
    raw_score: int
    band_score: float
    section_scores: Optional[dict]
    graded_at: datetime