from pydantic import BaseModel, Field
from typing import List, Optional, Literal


FundingPathwayType = Literal["self_funded", "scholarship", "sponsor", "blocked_account"]
# 2. Define how a specific amount of money is represented
class FundingAmount(BaseModel):
    amount: float
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217, e.g. GBP")
    period: Literal["per_month", "per_year", "total"]
    qualifier: Optional[str] = Field(None, description="e.g. 'London', 'outside London', 'first year'")
# 3. Define a pathway (which holds a list of amounts)
class FundingPathway(BaseModel):
    pathway: FundingPathwayType
    amounts: List[FundingAmount] = []
    # e.g., "bank statement", "blocked account certificate"
    accepted_evidence: Optional[List[str]] = None
    notes: Optional[str] = None
# 4. The top-level ProofOfFunds just holds a list of pathways
class ProofOfFunds(BaseModel):
    pathways: List[FundingPathway] = []
    notes: Optional[str] = None



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
    extraction_evidence: Optional[dict] = Field(None, description="Verbatim evidence mapping")
    egyptian_specific: bool = Field(..., description="True if this record is Egypt-applicant specific")
