from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class ExamSpeakingTranscript:
    id: UUID
    session_id: UUID
    part: int
    transcript_text: str
    duration_s: int
    question_text: str
    created_at: datetime
