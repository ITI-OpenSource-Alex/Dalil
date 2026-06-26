from pydantic import BaseModel
from typing import Optional


class EssayCreate(BaseModel):
    userId: str
    essayText: str
    submissionType: str
    examSessionId: Optional[str] = None