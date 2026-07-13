from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class ChatRequest(BaseModel):
    userId: str = Field(..., description="Unique ID of the user")
    sessionId: str = Field(..., description="Unique ID of the session")
    message: str = Field(..., description="User's input text message")
    attachments: Optional[List[str]] = Field(default=None, description="Optional list of attachment URLs")

class HistoryResponseItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatStreamEvent(BaseModel):
    type: Literal["metadata", "token", "error", "speaking_url", "writing_url", "match_results", "sources"]
    intent: Optional[str] = None
    confidence: Optional[float] = None
    content: Optional[str] = None
    error: Optional[str] = None
    wsUrl: Optional[str] = None
    essayId: Optional[str] = None
    sseUrl: Optional[str] = None
    programs: Optional[List[dict]] = None
    sources: Optional[List[dict]] = None

