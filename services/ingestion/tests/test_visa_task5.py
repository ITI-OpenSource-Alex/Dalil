import pytest
import uuid
from app.adapters.visa_adapter import VisaSourceAdapter, ExtractionOutcome
from app.schemas.visa_schema import ProofOfFunds, FundingPathway, FundingAmount
from handler import fetch_all_adapters

def test_document_text_contains_amount_currency_and_qualifier():
    adapter = VisaSourceAdapter()
    outcome = ExtractionOutcome(
        source_id=uuid.uuid4(),
        country="United Kingdom",
        visa_type="Student",
        issuing_body="UK Home Office",
        source_url="https://www.gov.uk/student-visa",
        extraction_valid=True,
        proof_of_funds=ProofOfFunds(
            pathways=[
                FundingPathway(
                    pathway="self_funded",
                    amounts=[
                        FundingAmount(amount=1334.0, currency="GBP", period="per_month", qualifier="London")
                    ]
                )
            ]
        ),
        processing_days_min=15,
        processing_days_max=30
    )
    
    doc_dict = adapter._to_document_dict(outcome)
    content = doc_dict["content"]
    
    assert "1334.0 GBP per_month (London)" in content
    assert "Processing time: 15–30 days" in content
    assert "Official source: https://www.gov.uk/student-visa" in content

@pytest.mark.asyncio
async def test_handler_preserves_source_url_metadata(mocker):
    # Mock VisaSourceAdapter.scrape to return a visa doc dict
    mocker.patch("handler.IELTSOrgAdapter.scrape", mocker.AsyncMock(return_value=[]))
    mocker.patch("handler.DAADAdapter.scrape", mocker.AsyncMock(return_value=[]))
    mocker.patch("handler.CheveningAdapter.scrape", mocker.AsyncMock(return_value=[]))
    mocker.patch("handler.StudyInPolandAdapter.scrape", mocker.AsyncMock(return_value=[]))
    mocker.patch("handler.StipendiumHungaricumAdapter.scrape", mocker.AsyncMock(return_value=[]))
    mocker.patch("handler.MastersPortalAdapter.scrape", mocker.AsyncMock(return_value=[]))
    mocker.patch("handler.VisaSourceAdapter.scrape", mocker.AsyncMock(return_value=[{
        "content": "Test content",
        "source_url": "https://gov.uk/visa",
        "category": "visa",
        "visa_requirements": []
    }]))
    
    docs, visa_records = await fetch_all_adapters()
    assert len(docs) == 1
    assert docs[0].metadata["source_url"] == "https://gov.uk/visa"
