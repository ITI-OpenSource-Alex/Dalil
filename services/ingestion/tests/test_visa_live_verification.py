import os
import uuid
import pytest
from dotenv import load_dotenv
from app.adapters.visa_adapter import VisaSourceAdapter, VisaSource

load_dotenv()

@pytest.mark.asyncio
async def test_gated_live_visa_verification():
    """Task 8: Gated live extraction verification against live embassy sources.
    Skipped by default in regular test runs unless RUN_LIVE_LLM_TESTS=true environment variable is set."""
    if os.getenv("RUN_LIVE_LLM_TESTS", "").strip().lower() not in ("true", "1"):
        pytest.skip("Gated live verification skipped (set RUN_LIVE_LLM_TESTS=true or 1 to run live LLM test)")
    
    adapter = VisaSourceAdapter()
    live_source = VisaSource(
        id=uuid.uuid4(),
        country="United Kingdom",
        visa_type="Student",
        issuing_body="UK Home Office",
        source_url="https://www.gov.uk/student-visa/money",
        fetch_method="httpx"
    )
    
    outcomes1 = await adapter.run([live_source])
    assert len(outcomes1) == 1
    outcome1 = outcomes1[0]
    
    assert outcome1.extraction_valid is True
    assert outcome1.proof_of_funds is not None
    assert len(outcome1.proof_of_funds.pathways) > 0
    assert outcome1.content_hash is not None

    # Pass 2: Re-run with outcome1's content_hash set on the VisaSource
    live_source_unchanged = VisaSource(
        id=live_source.id,
        country=live_source.country,
        visa_type=live_source.visa_type,
        issuing_body=live_source.issuing_body,
        source_url=live_source.source_url,
        fetch_method=live_source.fetch_method,
        content_hash=outcome1.content_hash
    )

    outcomes2 = await adapter.run([live_source_unchanged])
    # The adapter detects identical hash, calls touch client, and skips LLM extraction
    assert len(outcomes2) == 0
