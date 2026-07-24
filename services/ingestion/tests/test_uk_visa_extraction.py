import pytest
import uuid
from pathlib import Path
from langchain_core.documents import Document
from app.adapters.visa_adapter import VisaSourceAdapter, VisaSource
from app.evidence import validate_evidence

@pytest.mark.asyncio
async def test_uk_student_visa_extraction_and_document_pipeline(mocker):
    """E2E Fixture pipeline test: HTML fixture -> adapter -> evidence validation -> handler metadata preservation."""
    fixture_path = Path(__file__).parent / "fixtures" / "uk_student_visa_page.html"
    fixture_html = fixture_path.read_text(encoding="utf-8")
    visible_text = VisaSourceAdapter._visible_text(fixture_html)

    adapter = VisaSourceAdapter()
    source = VisaSource(
        id=uuid.uuid4(),
        country="United Kingdom",
        visa_type="Student",
        issuing_body="UK Home Office",
        source_url="https://www.gov.uk/student-visa/money",
        fetch_method="httpx"
    )

    mocker.patch.object(adapter, "_fetch_text", return_value=visible_text)
    
    quote1 = "£1,334 per month (for up to 9 months) for courses in London"
    quote2 = "£1,023 per month (for up to 9 months) for courses outside London"
    quote3 = "had the money for at least 28 consecutive days"
    
    mock_llm_response = {
        "extraction_valid": True,
        "requirements": {
            "financial_holding_period": "28 consecutive days"
        },
        "proof_of_funds": {
            "pathways": [
                {
                    "pathway": "self_funded",
                    "amounts": [
                        {"amount": 1334.0, "currency": "GBP", "period": "per_month", "qualifier": "London"},
                        {"amount": 1023.0, "currency": "GBP", "period": "per_month", "qualifier": "outside London"}
                    ],
                    "accepted_evidence": ["bank statement"],
                    "notes": "Money must be held for at least 28 consecutive days."
                }
            ]
        },
        "processing_days_min": 15,
        "processing_days_max": 20,
        "extraction_evidence": {
            "requirements.financial_holding_period": quote3,
            "proof_of_funds.pathways[0].pathway": quote1,
            "proof_of_funds.pathways[0].amounts[0].amount": quote1,
            "proof_of_funds.pathways[0].amounts[0].currency": quote1,
            "proof_of_funds.pathways[0].amounts[0].period": quote1,
            "proof_of_funds.pathways[0].amounts[0].qualifier": quote1,
            "proof_of_funds.pathways[0].amounts[1].amount": quote2,
            "proof_of_funds.pathways[0].amounts[1].currency": quote2,
            "proof_of_funds.pathways[0].amounts[1].period": quote2,
            "proof_of_funds.pathways[0].amounts[1].qualifier": quote2,
            "proof_of_funds.pathways[0].accepted_evidence[0]": quote1,
            "proof_of_funds.pathways[0].notes": quote3,
            "processing_days_min": quote1,
            "processing_days_max": quote1
        }
    }

    mocker.patch.object(adapter, "_call_llm", return_value=(mock_llm_response, {}))

    outcomes = await adapter.run([source])
    assert len(outcomes) == 1
    outcome = outcomes[0]

    assert outcome.extraction_valid is True
    assert outcome.proof_of_funds is not None
    
    pathway = outcome.proof_of_funds.pathways[0]
    assert len(pathway.amounts) == 2
    assert pathway.amounts[0].amount == 1334.0
    assert pathway.amounts[0].currency == "GBP"
    assert pathway.amounts[0].qualifier == "London"
    
    assert pathway.amounts[1].amount == 1023.0
    assert pathway.amounts[1].currency == "GBP"
    assert pathway.amounts[1].qualifier == "outside London"

    # Evidence validation should pass cleanly
    validate_evidence(outcome, visible_text)

    # Verify rendered document dict
    doc_dict = adapter._to_document_dict(outcome)
    content = doc_dict["content"]

    assert "1334.0 GBP per_month (London)" in content
    assert "1023.0 GBP per_month (outside London)" in content
    assert "Official source: https://www.gov.uk/student-visa/money" in content

    # Test handler provenance dict transformation
    doc = Document(
        page_content=doc_dict['content'],
        metadata={'source_url': doc_dict.get('source_url') or doc_dict.get('url'), 'category': doc_dict.get('category')}
    )
    assert doc.metadata["source_url"] == "https://www.gov.uk/student-visa/money"
