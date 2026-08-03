from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ExamType, SkillArea


class QuestionResponse(BaseModel):
    """Public exam question payload returned to clients."""

    id: UUID
    book_ref: str
    test_number: int
    exam_type: ExamType
    skill_area: SkillArea
    passage_text: str | None = None
    audio_s3_key: str | None = None
    questions: list[dict[str, Any]]


class QuestionWithAnswerKey(QuestionResponse):
    """Internal exam question payload that includes grading answers."""

    answer_key: dict[str, Any]
