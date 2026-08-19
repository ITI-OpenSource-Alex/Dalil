from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ExamType, SessionStatus, SkillArea
from app.schemas.question import QuestionResponse


class CreateSessionRequest(BaseModel):
    """Request payload for creating a new IELTS exam session."""

    user_id: UUID
    exam_type: ExamType
    skill_area: SkillArea


class CreateSessionResponse(BaseModel):
    """Response payload for creating a new IELTS exam session."""

    session_id: UUID
    first_question_set: QuestionResponse


class SessionResponse(BaseModel):
    """Summary payload for an IELTS exam session."""

    id: UUID
    user_id: UUID
    exam_type: ExamType
    skill_area: SkillArea
    status: SessionStatus
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    time_limit_seconds: int


class SessionDetailsResponse(SessionResponse):
    """Detailed IELTS exam session payload with associated questions."""

    questions: list[QuestionResponse]


class SubmitAnswersRequest(BaseModel):
    """Request payload for submitting answers for an IELTS exam session."""

    # Writing submissions are per-task (essay_text/task_number) and never
    # populate this -- it was previously required with no default, which
    # meant a spec-correct Writing-only submission still 422'd unless the
    # caller sent a meaningless empty object alongside it. Defaulting to {}
    # keeps Reading (which always sends a populated dict) unaffected while
    # making the two submission shapes genuinely independent.
    answers: dict[str, Any] = Field(default_factory=dict)
    essay_text: str | None = None
    task_number: int | None = None
