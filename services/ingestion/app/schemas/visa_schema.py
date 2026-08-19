from pydantic import BaseModel, Field
from typing import List, Optional, Literal



FundingPathwayType = Literal["self_funded", "scholarship", "sponsor", "blocked_account"]

class FundingAmount(BaseModel):
    amount: float
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217, e.g. GBP")
    period: Literal["per_month", "per_year", "total"]
    qualifier: Optional[str] = Field(None, description="e.g. 'London', 'outside London', 'first year'")


class FundingPathway(BaseModel):
    pathway: FundingPathwayType
    amounts: List[FundingAmount] = []
    # e.g., "bank statement", "blocked account certificate"
    accepted_evidence: Optional[List[str]] = None
    notes: Optional[str] = None

class ProofOfFunds(BaseModel):
    pathways: List[FundingPathway] = []
    notes: Optional[str] = None



def funding_schema_prompt_block() -> str:
    """Return a compact JSON string representing the ProofOfFunds schema for the prompt."""
    return '''{
    "pathways": [
      {
        "pathway": "self_funded | scholarship | sponsor | blocked_account",
        "amounts": [
          {
            "amount": 0.0,
            "currency": "XXX",
            "period": "per_month | per_year | total",
            "qualifier": "optional string"
          }
        ],
        "accepted_evidence": ["string"],
        "notes": "optional string"
      }
    ],
    "notes": "optional string"
  }'''