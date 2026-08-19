import pytest
from pydantic import BaseModel
from app.evidence import validate_evidence, get_non_null_leaf_paths

class MockProofOfFunds(BaseModel):
    amount_eur: float | None = None
    notes: str | None = None

class MockExtractionOutcome(BaseModel):
    source_id: str = "123"
    country: str = "Germany"
    visa_type: str = "Student"
    issuing_body: str = "Embassy"
    source_url: str = "http://example.com"
    extraction_valid: bool = True
    requirements: dict[str, str] = {}
    proof_of_funds: MockProofOfFunds | None = None
    notes: str | None = None
    extraction_evidence: dict[str, str] | None = None

def test_get_non_null_leaf_paths():
    """Extracts JSON paths for all non-null leaf fields excluding identity metadata."""
    outcome = MockExtractionOutcome(
        requirements={"aps_certificate": "Required for Egyptian applicants"},
        proof_of_funds=MockProofOfFunds(notes="Must be blocked account"),
        notes="Bring photos"
    )
    paths = get_non_null_leaf_paths(outcome)
    assert paths == {
        "requirements.aps_certificate": "Required for Egyptian applicants",
        "proof_of_funds.notes": "Must be blocked account",
        "notes": "Bring photos"
    }

def test_validate_evidence_success():
    """Valid evidence matching JSON paths and exact verbatim case passes."""
    source_text = "Required for Egyptian applicants. Must be blocked account. Bring photos."
    outcome = MockExtractionOutcome(
        requirements={"aps_certificate": "Required for Egyptian applicants"},
        proof_of_funds=MockProofOfFunds(notes="Must be blocked account"),
        notes="Bring photos",
        extraction_evidence={
            "requirements.aps_certificate": "Required for Egyptian applicants",
            "proof_of_funds.notes": "Must be blocked account",
            "notes": "Bring photos"
        }
    )
    # Should pass cleanly without raising
    validate_evidence(outcome, source_text)

def test_validate_evidence_missing_evidence_raises():
    """Non-null extracted leaf fields missing from extraction_evidence raise ValueError."""
    source_text = "Required for Egyptian applicants. Must be blocked account."
    outcome = MockExtractionOutcome(
        requirements={"aps_certificate": "Required for Egyptian applicants"},
        proof_of_funds=MockProofOfFunds(notes="Must be blocked account"),
        extraction_evidence={
            "requirements.aps_certificate": "Required for Egyptian applicants"
            # Missing "proof_of_funds.notes"
        }
    )
    with pytest.raises(ValueError) as exc_info:
        validate_evidence(outcome, source_text)
    assert "Missing evidence entry for leaf field" in str(exc_info.value)

def test_validate_evidence_orphan_evidence_raises():
    """Evidence keys that do not correspond to any non-null leaf field raise ValueError."""
    source_text = "Required for Egyptian applicants. Extra text."
    outcome = MockExtractionOutcome(
        requirements={"aps_certificate": "Required for Egyptian applicants"},
        extraction_evidence={
            "requirements.aps_certificate": "Required for Egyptian applicants",
            "orphan_key": "Extra text"
        }
    )
    with pytest.raises(ValueError) as exc_info:
        validate_evidence(outcome, source_text)
    assert "Orphan evidence key" in str(exc_info.value)

def test_validate_evidence_case_sensitive_mismatch_raises():
    """Quotes that do not match exact case in source text raise ValueError (case-sensitive verbatim)."""
    source_text = "An APS Certificate is required."
    outcome = MockExtractionOutcome(
        requirements={"aps": "an aps certificate is required"},
        extraction_evidence={
            "requirements.aps": "an aps certificate is required"
        }
    )
    with pytest.raises(ValueError) as exc_info:
        validate_evidence(outcome, source_text)
    assert "not found verbatim in source text" in str(exc_info.value)

def test_validate_evidence_too_long_raises():
    """Quotes exceeding 20 words raise ValueError."""
    quote = "word " * 21
    source_text = quote.strip()
    outcome = MockExtractionOutcome(
        notes="word",
        extraction_evidence={
            "notes": source_text
        }
    )
    with pytest.raises(ValueError) as exc_info:
        validate_evidence(outcome, source_text)
    assert "exceeds 20 words" in str(exc_info.value)

def test_validate_evidence_whitespace_runs_tolerance():
    """Quote with single space matches source text containing a line break mid-phrase."""
    source_text = "The applicant must prove they have\n1000 GBP in a blocked account."
    quote = "they have 1000 GBP"
    outcome = MockExtractionOutcome(
        notes="1000 GBP",
        extraction_evidence={
            "notes": quote
        }
    )
    # Should pass without raising exception due to whitespace normalization
    validate_evidence(outcome, source_text)
