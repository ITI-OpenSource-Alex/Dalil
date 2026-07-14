from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EssayCreate(BaseModel):
    userId: str
    essayText: str
    submissionType: str
    examSessionId: Optional[str] = None


class EssayEvaluationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    userId: str = Field(min_length=1, max_length=128)
    essayText: str = Field(min_length=1, max_length=10000)
    submissionType: str = Field(min_length=1, max_length=64)
    examType: str = Field(min_length=1, max_length=64)


class HighlightedIssue(BaseModel):
    text: str
    issue: str
    suggestion: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class CriterionEvaluation(BaseModel):
    criterion: Literal[
        "task_response",
        "cohesion",
        "vocabulary",
        "grammar",
    ]
    band_score: float = Field(ge=0.0, le=9.0)
    feedback: str
    highlighted_issues: list[HighlightedIssue]


class EssayEvaluationResponse(BaseModel):
    essay_id: int
    evaluations: list[CriterionEvaluation]
    overall_band: float = Field(ge=0.0, le=9.0)
    from_cache: bool


class CVUploadResponse(BaseModel):
    cvId: int
    status: str
