from pydantic import BaseModel, Field
from typing import List, Optional, Literal


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

class HistoryResponseItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatStreamEvent(BaseModel):
    type: Literal["metadata", "token", "error", "speaking_url", "writing_url", "match_results", "sources", "exam_prep"]
    intent: Optional[str] = None
    confidence: Optional[float] = None
    content: Optional[str] = None
    error: Optional[str] = None
    wsUrl: Optional[str] = None
    essayId: Optional[str] = None
    sseUrl: Optional[str] = None
    programs: Optional[List[dict]] = None
    sources: Optional[List[dict]] = None

