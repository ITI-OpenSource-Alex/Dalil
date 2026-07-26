from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.reading import QuestionResult, SectionBreakdown


class ListeningStartResponse(BaseModel):
    session_id: UUID
    audio_urls: list[str]
    questions: list[dict[str, Any]]
    time_limit_seconds: int
    audio_url_expiry_seconds: int


class ListeningSubmitRequest(BaseModel):
    answers: dict[str, str]


class ListeningSubmitResponse(BaseModel):
    raw_score: int
    band_score: float
    per_question_result: dict[str, QuestionResult]
    section_breakdown: dict[str, SectionBreakdown]
