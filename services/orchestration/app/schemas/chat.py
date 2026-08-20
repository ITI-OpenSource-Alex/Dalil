from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Literal


ExplanationLimitation = Annotated[str, Field(min_length=1, max_length=500)]


class ExplanationFact(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    value: str = Field(..., min_length=1, max_length=500)
    sourceUrl: Optional[str] = Field(default=None, max_length=500)


class ExplanationContext(BaseModel):
    kind: Literal[
        "speaking_score",
        "writing_score",
        "exam_score",
        "programme_match",
        "cv_review",
        "recommendation",
        "checklist",
        "visa_requirement",
    ]
    title: str = Field(..., min_length=1, max_length=160)
    subjectId: Optional[str] = Field(default=None, max_length=160)
    summary: Optional[str] = Field(default=None, max_length=600)
    facts: List[ExplanationFact] = Field(min_length=1, max_length=24)
    limitations: List[ExplanationLimitation] = Field(default_factory=list, max_length=12)


class ChatRequest(BaseModel):
    userId: str = Field(..., description="Unique ID of the user")
    sessionId: str = Field(..., description="Unique ID of the session")
    # Enforced here as well as at the Gateway, and that is not redundant.
    # Services on the Docker network can call orchestration:8083 directly,
    # bypassing every Gateway control -- the same reasoning that put GOA-038's
    # fact-type allow-list in a CHECK constraint rather than trusting its
    # caller. A limit next to the field is also the one a developer will
    # actually see when they change this schema.
    #
    # Max only. A min_length would reject "" while letting "   " through to a
    # model call: a rule that looks like input hygiene and isn't. Whether input
    # is meaningful is the sanitizer's decision, made in one place.
    message: str = Field(..., max_length=2000, description="User's input text message")
    attachments: Optional[List[str]] = Field(default=None, description="Optional list of attachment URLs")
    explanationContext: Optional[ExplanationContext] = Field(
        default=None,
        description="Visible, turn-scoped evidence attached by an explainable UI claim",
    )

class HistoryResponseItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatStreamEvent(BaseModel):
    type: Literal["status", "metadata", "token", "error", "speaking_url", "writing_url", "match_results", "sources", "exam_prep", "general"]
    stage: Optional[Literal["connecting", "routing", "retrieving", "generating"]] = None
    message: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    content: Optional[str] = None
    error: Optional[str] = None
    wsUrl: Optional[str] = None
    essayId: Optional[str] = None
    sseUrl: Optional[str] = None
    programs: Optional[List[dict]] = None
    sources: Optional[List[dict]] = None

