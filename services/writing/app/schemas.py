from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EssayCreate(BaseModel):
    userId: str
    essayText: str
    submissionType: str
    examSessionId: Optional[str] = None

# TODO (GOA-112): Add EssayCreateRequest {userId, essayText, submissionType (task1|task2), examSessionId (optional)}
# and EssayCreateResponse {id, status} — field names per GOA-008's original spec, since GOA-018's Orchestration caller sends exactly that shape.

class EssayCreateRequest(BaseModel):
    userId: str
    essayText: str
    submissionType: str
    examSessionId: Optional[str] = None

class EssayCreateResponse(BaseModel):
    id: int
    status: str



class EssayEvaluationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    userId: str = Field(min_length=1, max_length=128)
    essayText: str = Field(min_length=1, max_length=10000)
    submissionType: str = Field(min_length=1, max_length=64)
    examType: str = Field(min_length=1, max_length=64)


class InlineIssue(BaseModel):
    text: str
    issue_type: str
    suggestion: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)


# Alias kept for backwards-compat imports elsewhere in the codebase.
HighlightedIssue = InlineIssue


class CriterionEvaluation(BaseModel):
    criterion: Literal[
        "task_response",
        "cohesion",
        "vocabulary",
        "grammar",
    ]
    band_score: float = Field(ge=0.0, le=9.0)
    feedback: str
    improvement_tip: str
    word_count: int = Field(ge=0)
    inline_issues: list[InlineIssue]


class EssayEvaluationResponse(BaseModel):
    essay_id: int
    evaluations: list[CriterionEvaluation]
    overall_band: float = Field(ge=0.0, le=9.0)
    from_cache: bool


class CVUploadResponse(BaseModel):
    cvId: int
    status: str


class CVReviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    userId: str = Field(min_length=1, max_length=128)
    cvS3Key: str = Field(min_length=1, max_length=512)
    targetCountry: str = Field(min_length=1, max_length=128)
    targetField: str = Field(min_length=1, max_length=128)


class CVReviewSection(BaseModel):
    """One area of feedback, e.g. Experience or Education."""

    name: str
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CVReviewResponse(BaseModel):
    overallScore: int = Field(ge=0, le=100)
    sections: list[CVReviewSection]


class ExamTaskEvaluationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    userId: str = Field(min_length=1, max_length=128)
    essayText: str = Field(min_length=1, max_length=10000)
    examType: str = Field(min_length=1, max_length=64)
    examSessionId: str = Field(min_length=1, max_length=128)
    taskNumber: int = Field(ge=1, le=2)
    stimulusS3Key: Optional[str] = Field(default=None, max_length=512)
    taskPrompt: Optional[str] = Field(default=None, max_length=2000)


class ExamTaskEvaluationResponse(BaseModel):
    essay_id: int
    exam_session_id: str
    task_number: int
    evaluations: list[CriterionEvaluation]
    overall_band: float = Field(ge=0.0, le=9.0)
    from_cache: bool
