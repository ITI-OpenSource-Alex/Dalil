from pydantic import BaseModel, Field
from typing import Optional


class ProgramRequirementsUpsertRequest(BaseModel):
    university: str = Field(..., description="University name")
    country: str = Field(..., description="Country where the program is offered")
    degree_level: str = Field(..., description="Degree level (e.g. Master, Bachelor, PhD)")
    min_ects: Optional[int] = Field(None, description="Minimum required ECTS credits")
    min_gpa: Optional[float] = Field(None, description="Minimum required GPA")
    min_ielts: Optional[float] = Field(None, description="Minimum required IELTS score")
    required_citizenship: Optional[str] = Field(None, description="Required citizenship, if restricted")
    min_work_experience: Optional[int] = Field(None, description="Minimum required work experience in years")
    source_url: Optional[str] = Field(None, description="Source webpage URL")
    content_hash: Optional[str] = Field(None, description="SHA256 hash of the content to check updates")
