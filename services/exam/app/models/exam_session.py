from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass(slots=True)
class ExamSession:
    id: UUID
    user_id: UUID
    exam_type: str
    skill_area: str
    question_id: Optional[UUID]
    status: str
    started_at: Optional[datetime]
    submitted_at: Optional[datetime]
    time_limit_seconds: int
