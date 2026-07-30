from typing import Literal, Optional
from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    itemId: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    checked: bool = False


class ChecklistResponse(BaseModel):
    checklistId: str
    programId: str
    generatedBy: Literal["llm", "fallback"]
    items: list[ChecklistItem]


class ChecklistItemStateUpdate(BaseModel):
    checked: bool


# --- LLM structured-output schema -------------------------------------------------
# Deliberately separate from ChecklistItem: the LLM only ever produces generated text
# fields, never `checked`, and its item_id is untrusted input the generator
# normalizes/deduplicates before it becomes a persisted, API-facing ChecklistItem.itemId.

class GeneratedChecklistItem(BaseModel):
    item_id: str = Field(
        description="Short lowercase slug identifying this item, e.g. 'ielts_retake'."
    )
    title: str = Field(description="Short, actionable checklist item title.")
    description: Optional[str] = Field(
        None, description="One or two sentences explaining what to do and why."
    )
    category: Optional[str] = Field(
        None, description="Grouping label, e.g. 'language', 'documents', 'financial'."
    )


class GeneratedChecklist(BaseModel):
    items: list[GeneratedChecklistItem]
