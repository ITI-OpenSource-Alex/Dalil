from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ExamType


class ReadingStartRequest(BaseModel):
    exam_type: ExamType
    user_id: UUID


class ReadingStartResponse(BaseModel):
    session_id: UUID
    passages: list[str]
    questions: list[dict[str, Any]]
    time_limit_seconds: int


class ReadingSubmitRequest(BaseModel):
    answers: dict[str, str]


class QuestionResult(BaseModel):
    submitted_answer: str
    correct_answer: str
    is_correct: bool


class SectionBreakdown(BaseModel):
    correct: int
    total: int


class ReadingSubmitResponse(BaseModel):
    raw_score: int
    band_score: float
    per_question_result: dict[str, QuestionResult]
    section_breakdown: dict[str, SectionBreakdown]
