import pytest
from pydantic import ValidationError

from app.schemas.visa import VisaRequirementsRequest

VALID_PAYLOAD = {
    "country": "Germany",
    "visa_type": "Student",
    "issuing_body": "German Embassy Cairo",
    "requirements": {"passport": True, "funds_eur": 11208},
    "proof_of_funds": {
        "amount_eur": 11208.0,
        "accepted_account_types": ["blocked_account"],
        "blocked_account_providers": ["Fintiba"],
        "minimum_balance_period_days": 365,
        "sponsor_letter_accepted": False,
        "notes_egypt": "EGP transfers must be converted to EUR before deposit."
    },
    "source_url": "https://germany.info",
    "processing_days_min": 30,
    "processing_days_max": 90,
    "notes": "Bring physical biometric photos.",
    "content_hash": "abc123hash",
    "egyptian_specific": True
}


def test_valid_payload_passes_validation():
    request = VisaRequirementsRequest(**VALID_PAYLOAD)
    assert request.egyptian_specific is True
    assert request.proof_of_funds.amount_eur == 11208.0
    assert request.proof_of_funds.blocked_account_providers == ["Fintiba"]


def test_missing_egyptian_specific_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "egyptian_specific"}
    with pytest.raises(ValidationError):
        VisaRequirementsRequest(**payload)


def test_malformed_proof_of_funds_amount_raises_validation_error():
    payload = dict(VALID_PAYLOAD)
    payload["proof_of_funds"] = dict(VALID_PAYLOAD["proof_of_funds"])
    payload["proof_of_funds"]["amount_eur"] = "not-a-number"
    with pytest.raises(ValidationError):
        VisaRequirementsRequest(**payload)


def test_model_dump_produces_plain_nested_dict():
    request = VisaRequirementsRequest(**VALID_PAYLOAD)
    dumped = request.model_dump()

    assert isinstance(dumped, dict)
    assert dumped["egyptian_specific"] is True
    assert isinstance(dumped["proof_of_funds"], dict)
    assert dumped["proof_of_funds"]["amount_eur"] == 11208.0
    assert dumped["proof_of_funds"]["blocked_account_providers"] == ["Fintiba"]
    assert dumped["proof_of_funds"]["minimum_balance_period_days"] == 365
