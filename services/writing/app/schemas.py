from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EssayCreate(BaseModel):
    userId: str
    essayText: str
    submissionType: str
    examSessionId: Optional[str] = None

# TODO (GOA-112): Add EssayCreateRequest {userId, essayText, submissionType (task1|task2), examSessionId (optional)}
# and EssayCreateResponse {id, status} — field names per GOA-008's original spec, since GOA-018's Orchestration caller sends exactly that shape.

class EssayCreateRequest(BaseModel):
    userId: str
    essayText: str = Field(min_length=1, max_length=5000)
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
    inputSource: Literal["typed", "ocr"] = "typed"


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
    s3Key: str


class CVLatestResponse(BaseModel):
    """GET /cv/latest -- the signed-in user's most recent upload, if any.

    Lets the browser show upload status and recover cvS3Key (needed by
    POST /cv/review) across a page reload instead of holding it only in
    client state.
    """

    cvId: int
    s3Key: str
    originalFilename: str
    status: str
    uploadedAt: datetime
    errorMessage: Optional[str] = None


class CVReviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    userId: str = Field(min_length=1, max_length=128)
    cvS3Key: str = Field(min_length=1, max_length=512)
    programId: Optional[str] = Field(default=None, min_length=1, max_length=128)
    # Compatibility for older API clients. The product UI sends programId and
    # the service resolves the target from RAG rather than trusting form fields.
    targetCountry: Optional[str] = Field(default=None, min_length=1, max_length=128)
    targetField: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_program_or_legacy_target(self):
        if self.programId or (self.targetCountry and self.targetField):
            return self
        raise ValueError("programId is required")


class CVReviewSection(BaseModel):
    """One area of ticket-defined CV review feedback."""

    name: str = Field(min_length=1)
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
    inputSource: Literal["typed", "ocr"] = "typed"


class ExamTaskEvaluationResponse(BaseModel):
    essay_id: int
    exam_session_id: str
    task_number: int
    evaluations: list[CriterionEvaluation]
    overall_band: float = Field(ge=0.0, le=9.0)
    from_cache: bool


class EssayHistoryItem(BaseModel):
    """One row of GET /essays -- a summary, not the full essay text or
    evaluation. A per-essay fetch (not built yet) would return the detail."""

    id: int
    submitted_at: datetime
    status: str
    submission_type: Optional[str]
    exam_type: Optional[str]
    task_number: Optional[int]
    overall_band: Optional[float] = Field(default=None, ge=0.0, le=9.0)
    excerpt: str

# --- Motivation letter review (per-programme admissions feedback) -----------------
# Scores are 1-5 against admissions criteria and are deliberately NOT IELTS bands.
# overallScore is Optional and stays None unless at least three criteria produced a
# score: a mean of one or two is not an overall judgement.

class MotivationLetterCreateRequest(BaseModel):
    userId: str
    programId: Optional[str] = None
    content: str


class MotivationLetterResponse(BaseModel):
    letterId: int
    userId: str
    programId: Optional[str] = None
    status: str
    overallScore: Optional[float] = None
    criteria: list[dict] = []
    programmeSnapshot: Optional[dict] = None
    content: Optional[str] = None
    errorMessage: Optional[str] = None
    createdAt: Optional[str] = None
    completedAt: Optional[str] = None


class MotivationLetterSummary(BaseModel):
    letterId: int
    programId: Optional[str] = None
    status: str
    overallScore: Optional[float] = None
    createdAt: Optional[str] = None
