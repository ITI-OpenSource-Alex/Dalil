from pydantic import BaseModel, Field
from typing import Optional

class VisaRequirementsRequest(BaseModel):
    country: str = Field(..., description="Country name")
    visa_type: str = Field(..., description="Type of visa (e.g. Student, Work)")
    issuing_body: str = Field(..., description="Entity issuing the visa")
    requirements: dict = Field(..., description="Structured JSON requirements details")
    proof_of_funds: Optional[dict] = Field(None, description="JSON details on proof of funds")
    source_url: Optional[str] = Field(None, description="Source webpage URL")
    processing_days_min: Optional[int] = Field(None, description="Min processing days")
    processing_days_max: Optional[int] = Field(None, description="Max processing days")
    notes: Optional[str] = Field(None, description="Additional notes")
    content_hash: Optional[str] = Field(None, description="SHA256 hash of the content to check updates")
