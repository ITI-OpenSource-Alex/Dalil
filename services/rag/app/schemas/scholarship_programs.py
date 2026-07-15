from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ScholarshipProgramUpsertRequest(BaseModel):
    name: str = Field(..., description="Scholarship program name")
    provider: str = Field(..., description="Provider issuing the scholarship (e.g. DAAD, Chevening)")
    source_url: str = Field(..., description="Source webpage URL")
    country: Optional[str] = Field(None, description="Country the scholarship is offered in")
    degree_level: Optional[str] = Field(None, description="Degree level (e.g. Master, PhD)")
    award_amount: Optional[str] = Field(None, description="Free-text award amount/description")
    deadline: Optional[date] = Field(None, description="Application deadline")
    eligibility: dict = Field(default_factory=dict, description="Structured eligibility rules")
    citizenship_eligible: bool = Field(True, description="Open to Egyptian applicants")
    min_gpa: Optional[float] = Field(None, description="Minimum required GPA")
    min_ielts: Optional[float] = Field(None, description="Minimum required IELTS score")
    content_hash: Optional[str] = Field(None, description="SHA256 hash of the content to check updates")

    @field_validator("deadline", mode="before")
    @classmethod
    def coerce_unparseable_deadline_to_none(cls, value):
        """Scraped deadline text ("rolling", "TBC", inconsistent formats) is common and
        should not reject an otherwise-valid record -- fall back to None rather than
        raising a ValidationError."""
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                try:
                    return datetime.strptime(value, "%d %B %Y").date()
                except ValueError:
                    return None
        return None
