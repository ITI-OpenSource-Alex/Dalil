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
    # GOA-134: nullable. A speaking session where fewer than 3 of 4 criteria
    # completed has no band, and NULL is how that is represented now that
    # exam_results.band_score no longer forces a fabricated 0.0.
    band_score: Optional[float] = None
    section_scores: Optional[dict]
    graded_at: datetime
    agent_responses: dict | list | None = None
