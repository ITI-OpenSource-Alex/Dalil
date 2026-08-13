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
    generatedBy: Literal["llm", "fallback", "requirements"]
    items: list[ChecklistItem]


class ChecklistItemStateUpdate(BaseModel):
    checked: bool


# --- Financial Requirements (GOA-035) ----------------------------------------------
# Sourced entirely from visa_finance.get_student_visa_finance (GOA-108). Every field
# here is copied verbatim from a visa_requirements row -- there is no LLM in this
# path and no field a frontend or model could plausibly have invented.

class FinancialRequirementItem(BaseModel):
    type: str
    country: str
    issuingBody: str
    message: str
    sourceUrl: Optional[str] = None
    lastVerifiedAt: Optional[str] = None


class FinancialRequirementsResponse(BaseModel):
    programId: str
    items: list[FinancialRequirementItem]


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
