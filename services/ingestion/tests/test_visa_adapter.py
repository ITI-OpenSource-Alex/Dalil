import json
import uuid

import pytest

from app.adapters.visa_adapter import (
    EXTRACTION_SYSTEM_PROMPT,
    ExtractionOutcome,
    VisaSource,
    VisaSourceAdapter,
)
from app.schemas.visa_schema import ProofOfFunds, FundingPathway


@pytest.fixture
def dummy_source():
    return VisaSource(
        id=str(uuid.uuid4()),
        country="Germany",
        visa_type="National Visa (Study)",
        issuing_body="German Embassy Cairo",
        source_url="http://example.com/german-visa",
        fetch_method="httpx",
    )


def _llm(payload: dict):
    """_call_llm returns (parsed_json, telemetry)."""
    return (payload, {"model": "test", "latency_ms": 1, "input_tokens": 1, "output_tokens": 1})


@pytest.mark.asyncio
async def test_extraction_populates_fields_with_evidence(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    text = "German visa page text. proof of 11,208 EUR in a blocked account. An APS certificate is required."
    mocker.patch.object(adapter, "_fetch_text", return_value=text)
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "requirements": {"aps_certificate": "Required for Egyptian applicants"},
                "proof_of_funds": {
                    "pathways": [{
                        "pathway": "blocked_account",
                        "amounts": [{"amount": 11208.0, "currency": "EUR", "period": "per_year"}]
                    }]
                },
                "processing_days_min": 28,
                "processing_days_max": 42,
                "extraction_evidence": {
                    "requirements.aps_certificate": "An APS certificate is required",
                    "proof_of_funds.pathways[0].pathway": "proof of 11,208 EUR in a blocked account",
                    "proof_of_funds.pathways[0].amounts[0].amount": "proof of 11,208 EUR in a blocked account",
                    "proof_of_funds.pathways[0].amounts[0].currency": "proof of 11,208 EUR in a blocked account",
                    "proof_of_funds.pathways[0].amounts[0].period": "proof of 11,208 EUR in a blocked account",
                    "processing_days_min": "German visa page text.",
                    "processing_days_max": "German visa page text.",
                },
            }
        ),
    )

    outcomes = await adapter.run([dummy_source])

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.extraction_valid is True
    assert outcome.proof_of_funds.pathways[0].amounts[0].amount == 11208.0
    assert outcome.requirements["aps_certificate"]
    assert outcome.extraction_evidence.get("proof_of_funds.pathways[0].amounts[0].amount")
    assert outcome.source_url == "http://example.com/german-visa"


@pytest.mark.asyncio
async def test_absent_field_stays_null(mocker, dummy_source):
    """The anti-hallucination regression test: a field absent from the page stays null."""
    adapter = VisaSourceAdapter()
    mocker.patch.object(adapter, "_fetch_text", return_value="Text with no processing time")
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "requirements": {},
                "proof_of_funds": {"amount_eur": 11208.0},
                "processing_days_min": None,
                "processing_days_max": None,
                "extraction_evidence": {"proof_of_funds": "Requires 11208 EUR"},
            }
        ),
    )

    outcomes = await adapter.run([dummy_source])

    assert outcomes[0].processing_days_min is None
    assert outcomes[0].processing_days_max is None


def test_prompt_states_the_anti_hallucination_constraints():
    """The mocked tests above prove the plumbing handles nulls and evidence — they cannot
    prove the model was ever ASKED for them. This asserts the four hard constraints are
    actually present in the prompt that ships."""
    p = EXTRACTION_SYSTEM_PROMPT.lower()
    assert "only information explicitly present" in p
    assert "do not use outside knowledge" in p
    assert "return null" in p and "do not estimate" in p
    assert "verbatim quote" in p
    assert "extraction_valid" in p and "false" in p
    assert "never output a source url" in p


@pytest.mark.asyncio
async def test_source_url_always_overwritten(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    mocker.patch.object(adapter, "_fetch_text", return_value="Dummy text")
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "source_url": "http://hallucinated-url.com",
                "country": "Narnia",
                "issuing_body": "Made Up Embassy",
                "requirements": {},
            }
        ),
    )

    outcomes = await adapter.run([dummy_source])

    # Provenance and identity are stamped by code, never trusted from the model.
    assert outcomes[0].source_url == "http://example.com/german-visa"
    assert outcomes[0].country == "Germany"
    assert outcomes[0].issuing_body == "German Embassy Cairo"


@pytest.mark.asyncio
async def test_invalid_output_retries_once_then_fails(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    mocker.patch.object(adapter, "_fetch_text", return_value="Dummy text")
    mock_llm = mocker.patch.object(adapter, "_call_llm", side_effect=ValueError("Schema invalid"))

    outcomes = await adapter.run([dummy_source])

    assert mock_llm.call_count == 2  # initial + exactly one retry
    assert outcomes[0].extraction_valid is False


@pytest.mark.asyncio
async def test_retry_prompt_includes_the_validation_error(mocker, dummy_source):
    """The retry must feed the error back so the model can self-correct."""
    adapter = VisaSourceAdapter()
    mocker.patch.object(adapter, "_fetch_text", return_value="Page text")
    calls = []

    async def fake_llm(text, source):
        calls.append(text)
        raise ValueError("missing required field 'requirements'")

    mocker.patch.object(adapter, "_call_llm", side_effect=fake_llm)

    await adapter.run([dummy_source])

    assert len(calls) == 2
    assert "failed schema validation" in calls[1]
    assert "missing required field" in calls[1]


@pytest.mark.asyncio
async def test_validity_gate_rejects_wrong_content(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    mocker.patch.object(adapter, "_fetch_text", return_value="404 Page Not Found")
    mocker.patch.object(
        adapter, "_call_llm", return_value=_llm({"extraction_valid": False, "requirements": {}})
    )

    outcomes = await adapter.run([dummy_source])

    assert outcomes[0].extraction_valid is False
    assert outcomes[0].proof_of_funds is None


@pytest.mark.asyncio
async def test_empty_page_text_is_rejected_without_calling_llm(mocker, dummy_source):
    """No point spending a token on a blank fetch."""
    adapter = VisaSourceAdapter()
    mocker.patch.object(adapter, "_fetch_text", return_value="   \n  ")
    mock_llm = mocker.patch.object(adapter, "_call_llm")

    outcomes = await adapter.run([dummy_source])

    assert outcomes[0].extraction_valid is False
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_one_source_failure_doesnt_kill_run(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    source2 = dummy_source.model_copy(update={"id": str(uuid.uuid4())})
    source3 = dummy_source.model_copy(update={"id": str(uuid.uuid4())})

    mocker.patch.object(
        adapter,
        "_fetch_text",
        side_effect=["Success text 1", Exception("Network error on source 2"), "Success text 3"],
    )
    mocker.patch.object(
        adapter, "_call_llm", return_value=_llm({"extraction_valid": True, "requirements": {}})
    )

    outcomes = await adapter.run([dummy_source, source2, source3])

    assert len(outcomes) == 3
    assert outcomes[0].extraction_valid is True
    assert outcomes[1].extraction_valid is False  # failed fetch, run continues
    assert outcomes[2].extraction_valid is True


@pytest.mark.asyncio
async def test_scrape_reads_sources_and_returns_orchestrator_shape(mocker, dummy_source):
    """scrape() is what run_orchestrator actually calls. It must load the config table
    and return dicts carrying `content` + `visa_requirements` — the dual-write shape."""
    adapter = VisaSourceAdapter()
    mocker.patch(
        "app.adapters.visa_adapter.fetch_visa_sources",
        return_value=[dummy_source.model_dump()],
    )
    mocker.patch.object(adapter, "_fetch_text", return_value="German visa page text. 11,208 EUR.")
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "requirements": {"aps_certificate": "Required"},
                "proof_of_funds": {
                    "pathways": [{
                        "pathway": "blocked_account",
                        "amounts": [{"amount": 11208.0, "currency": "EUR", "period": "per_year"}]
                    }]
                },
                "extraction_evidence": {
                    "requirements.aps_certificate": "German visa page text.",
                    "proof_of_funds.pathways[0].pathway": "11,208 EUR",
                    "proof_of_funds.pathways[0].amounts[0].amount": "11,208 EUR",
                    "proof_of_funds.pathways[0].amounts[0].currency": "11,208 EUR",
                    "proof_of_funds.pathways[0].amounts[0].period": "11,208 EUR",
                },
            }
        ),
    )

    docs = await adapter.scrape()

    assert len(docs) == 1
    doc = docs[0]
    assert "content" in doc and doc["content"]
    assert doc["category"] == "visa"
    record = doc["visa_requirements"][0]
    assert record["country"] == "Germany"
    assert record["source_url"] == "http://example.com/german-visa"
    assert record["proof_of_funds"]["pathways"][0]["amounts"][0]["amount"] == 11208.0
    assert record["egyptian_specific"] is True


@pytest.mark.asyncio
async def test_scrape_omits_invalid_extractions(mocker, dummy_source):
    """An invalid extraction must not be upserted as a real requirements row."""
    adapter = VisaSourceAdapter()
    mocker.patch(
        "app.adapters.visa_adapter.fetch_visa_sources",
        return_value=[dummy_source.model_dump()],
    )
    mocker.patch.object(adapter, "_fetch_text", return_value="404 Not Found")
    mocker.patch.object(
        adapter, "_call_llm", return_value=_llm({"extraction_valid": False, "requirements": {}})
    )

    docs = await adapter.scrape()

    assert docs == []


@pytest.mark.asyncio
async def test_playwright_used_only_for_playwright_sources(mocker, dummy_source):
    """fetch_method drives the fetch path — VFS Global is the one JS-rendered source."""
    adapter = VisaSourceAdapter()
    pw = mocker.patch.object(adapter, "_fetch_text_playwright", return_value="rendered text")
    http_get = mocker.patch.object(adapter.client, "get")

    await adapter._fetch_text(dummy_source.model_copy(update={"fetch_method": "playwright"}))

    pw.assert_called_once()
    http_get.assert_not_called()


def test_visa_source_accepts_real_uuid_object():
    """asyncpg hands back uuid.UUID for a UUID column; a str-only model rejects every row."""
    real_uuid = uuid.uuid4()
    source = VisaSource(
        id=real_uuid,
        country="Germany",
        visa_type="National Visa (Study)",
        issuing_body="German Embassy Cairo",
        source_url="http://example.com",
        fetch_method="httpx",
    )
    assert str(source.id) == str(real_uuid)


def test_extraction_outcome_proof_of_funds_is_structured():
    """Guards the GOA-109/110 dependency: proof_of_funds must hold funding-pathway data,
    which a flat float cannot represent."""
    outcome = ExtractionOutcome(
        source_id=str(uuid.uuid4()),
        country="Hungary",
        visa_type="National Visa (Study)",
        issuing_body="Hungarian Consular Services",
        source_url="http://example.com",
        extraction_valid=True,
        proof_of_funds=ProofOfFunds(
            pathways=[FundingPathway(pathway="scholarship", notes="Stipendium Hungaricum award letter satisfies this requirement")]
        ),
    )
    assert outcome.proof_of_funds.pathways[0].notes
    assert outcome.proof_of_funds.model_dump()


# ---------------------------------------------------------------------------
# Ported from the deleted test_egypt_adapters.py / test_egypt_ingestion_e2e.py.
#
# Those suites tested bespoke per-embassy HTML parsing (extract_documents,
# _discover_study_pdf_url) that GOA-116 deliberately removed, so they cannot be
# ported literally — the functions are gone by design. What remains valuable is
# their FIXTURE HTML and known-correct expected values: they define what a correct
# extraction from a real embassy page looks like. Here they guard the one stage
# that still parses HTML in the new pipeline — _visible_text() — because if text
# reduction silently drops the facts, the LLM cannot extract what is not there and
# the failure looks like a model problem rather than a parsing bug.
# ---------------------------------------------------------------------------

GERMAN_EMBASSY_FIXTURE = """
    <html><body>
      <nav>Home | Contact | Impressum</nav>
      <script>var tracking = 1;</script>
      <style>.hidden{display:none}</style>
      <main>
        <h2>National Visa Requirements</h2>
        <p>Applicants must provide a valid passport and an APS certificate.</p>
        <ul>
          <li>Valid passport</li>
          <li>APS certificate</li>
          <li>Proof of funds: EUR 11208 in a blocked account</li>
        </ul>
        <p>Processing time: 15-20 working days.</p>
      </main>
      <footer>Deutsche Botschaft Kairo</footer>
    </body></html>
"""


def test_visible_text_preserves_the_facts_extraction_depends_on():
    """Golden-data port: every fact the old German Embassy Cairo adapter extracted must
    still survive text reduction, or the LLM has nothing to extract from."""
    text = VisaSourceAdapter._visible_text(GERMAN_EMBASSY_FIXTURE)

    assert "APS certificate" in text
    assert "Valid passport" in text
    assert "11208" in text
    assert "blocked account" in text
    assert "15-20" in text


def test_visible_text_strips_chrome_but_keeps_content():
    """Nav/script/style/footer are noise that wastes tokens and can mislead the model."""
    text = VisaSourceAdapter._visible_text(GERMAN_EMBASSY_FIXTURE)

    assert "var tracking" not in text
    assert "display:none" not in text
    assert "Impressum" not in text
    assert "National Visa Requirements" in text


def test_visible_text_truncates_runaway_pages():
    """Embassy pages with inlined PDFs can be enormous; the cap must hold."""
    from app.adapters.visa_adapter import MAX_TEXT_CHARS

    huge = "<html><body><main>" + ("requirement text " * 5000) + "</main></body></html>"
    text = VisaSourceAdapter._visible_text(huge)

    assert len(text) <= MAX_TEXT_CHARS


@pytest.mark.asyncio
async def test_end_to_end_german_fixture_produces_expected_visa_record(mocker, dummy_source):
    """Golden-data port of the deleted happy-path e2e test: the same fixture, the same
    expected values, asserted against the new generic pipeline end to end."""
    adapter = VisaSourceAdapter()
    mocker.patch(
        "app.adapters.visa_adapter.fetch_visa_sources",
        return_value=[dummy_source.model_dump()],
    )

    async def fake_fetch(source):
        return VisaSourceAdapter._visible_text(GERMAN_EMBASSY_FIXTURE)

    mocker.patch.object(adapter, "_fetch_text", side_effect=fake_fetch)
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "requirements": {
                    "items": ["Valid passport", "APS certificate"],
                    "aps_certificate": "Required",
                },
                "proof_of_funds": {
                    "pathways": [{
                        "pathway": "blocked_account",
                        "amounts": [{"amount": 11208.0, "currency": "EUR", "period": "per_year"}]
                    }]
                },
                "processing_days_min": 15,
                "processing_days_max": 20,
                "extraction_evidence": {
                    "proof_of_funds.pathways[0].pathway": "blocked account",
                    "proof_of_funds.pathways[0].amounts[0].amount": "EUR 11208",
                    "proof_of_funds.pathways[0].amounts[0].currency": "EUR 11208",
                    "proof_of_funds.pathways[0].amounts[0].period": "EUR 11208",
                    "processing_days_min": "15-20 working days",
                    "processing_days_max": "15-20 working days",
                    "requirements.items[0]": "Valid passport",
                    "requirements.items[1]": "APS certificate",
                    "requirements.aps_certificate": "APS certificate"
                },
            }
        ),
    )

    docs = await adapter.scrape()

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Germany"
    assert "APS certificate" in doc["content"]

    record = doc["visa_requirements"][0]
    assert record["country"] == "Germany"
    assert record["issuing_body"] == "German Embassy Cairo"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 15
    assert record["processing_days_max"] == 20
    assert record["proof_of_funds"]["pathways"][0]["amounts"][0]["amount"] == 11208.0
    assert "Valid passport" in record["requirements"]["items"]


@pytest.mark.asyncio
async def test_missing_fields_yield_nulls_not_guesses(mocker, dummy_source):
    """Golden-data port: the old suite asserted a page without processing time / funds
    produced None for those, never an invented 'typical' figure."""
    adapter = VisaSourceAdapter()
    sparse = "<html><body><main><ul><li>Valid passport</li></ul></main></body></html>"
    mocker.patch.object(
        adapter, "_fetch_text", return_value=VisaSourceAdapter._visible_text(sparse)
    )
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "requirements": {"items": ["Valid passport"]},
                "proof_of_funds": None,
                "processing_days_min": None,
                "processing_days_max": None,
                "extraction_evidence": {"requirements.items[0]": "Valid passport"},
            }
        ),
    )

    outcomes = await adapter.run([dummy_source])

    assert outcomes[0].processing_days_min is None
    assert outcomes[0].processing_days_max is None
    assert outcomes[0].proof_of_funds is None
    assert "Valid passport" in outcomes[0].requirements["items"]

def test_extraction_model_is_config_driven():
    from app.adapters.visa_adapter import EXTRACTION_MODEL
    import os
    assert EXTRACTION_MODEL == os.environ.get("EXTRACTION_MODEL", "claude-opus-4-8")

@pytest.mark.asyncio
async def test_extraction_evidence_quotes_are_verbatim(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    text = "The applicant must provide a valid passport and two photos."
    mocker.patch.object(adapter, "_fetch_text", return_value=text)
    mocker.patch.object(
        adapter,
        "_call_llm",
        return_value=_llm(
            {
                "extraction_valid": True,
                "requirements": {"passport": "valid passport", "photos": "two photos"},
                "extraction_evidence": {
                    "requirements.passport": "valid passport",
                    "requirements.photos": "two photos"
                }
            }
        ),
    )
    
    outcomes = await adapter.run([dummy_source])
    assert len(outcomes) == 1
    evidence = outcomes[0].extraction_evidence
    for key, quote in evidence.items():
        assert quote in text, f"Quote '{quote}' for '{key}' not found in source text!"

@pytest.mark.asyncio
async def test_usage_tokens_recorded_in_telemetry(mocker, dummy_source):
    adapter = VisaSourceAdapter()
    text = "Some source text"
    mocker.patch.object(adapter, "_fetch_text", return_value=text)
    
    class MockUsage:
        input_tokens = 123
        output_tokens = 456
    
    class MockMessage:
        text = '{"extraction_valid": true}'
    
    class MockContent:
        content = [MockMessage()]
        usage = MockUsage()
    
    class MockMessages:
        async def create(self, **kwargs):
            return MockContent()
    
    class MockAnthropic:
        messages = MockMessages()
        
    adapter.anthropic = MockAnthropic()
    
    raw_data, telemetry = await adapter._call_llm(text, dummy_source)
    assert telemetry["input_tokens"] == 123
    assert telemetry["output_tokens"] == 456
