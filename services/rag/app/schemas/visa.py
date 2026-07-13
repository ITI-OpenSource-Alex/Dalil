from pydantic import BaseModel, Field
from typing import List, Optional


class ProofOfFunds(BaseModel):
    amount_eur: Optional[float] = Field(None, description="Required proof-of-funds amount in EUR")
    accepted_account_types: Optional[List[str]] = Field(None, description="Account types accepted as proof of funds")
    blocked_account_providers: Optional[List[str]] = Field(None, description="Approved blocked-account providers (e.g. Fintiba)")
    minimum_balance_period_days: Optional[int] = Field(None, description="Minimum number of days the balance must be held")
    sponsor_letter_accepted: Optional[bool] = Field(None, description="Whether a sponsor letter is accepted in lieu of a blocked account")
    notes_egypt: Optional[str] = Field(None, description="Egypt-specific notes on proof-of-funds requirements")


class VisaRequirementsRequest(BaseModel):
    country: str = Field(..., description="Country name")
    visa_type: str = Field(..., description="Type of visa (e.g. Student, Work)")
    issuing_body: str = Field(..., description="Entity issuing the visa")
    requirements: dict = Field(..., description="Structured JSON requirements details")
    proof_of_funds: Optional[ProofOfFunds] = Field(None, description="Structured proof-of-funds details")
    source_url: Optional[str] = Field(None, description="Source webpage URL")
    processing_days_min: Optional[int] = Field(None, description="Min processing days")
    processing_days_max: Optional[int] = Field(None, description="Max processing days")
    notes: Optional[str] = Field(None, description="Additional notes")
    content_hash: Optional[str] = Field(None, description="SHA256 hash of the content to check updates")
    egyptian_specific: bool = Field(..., description="True if this record is Egypt-applicant specific")
