"""
GOA-086 Task 18 -- end-to-end tests for the wired Egypt visa ingestion pipeline.

Each of the 9 Egypt adapters runs its REAL extract_documents() logic against fixture
HTML (no real network calls -- only fetch_page/robots and the RAG-service-facing client
calls are mocked, matching the existing test_ingestion.py / test_orchestrator.py
patterns). This proves the real adapter output shape is exactly what the wiring code in
handler.py and run_orchestrator.py (Task 16) expects and correctly dual-writes.
"""
import pytest

from app.adapters.german_embassy_cairo import GermanEmbassyCairoAdapter
from app.adapters.aps_cairo import APSCairoAdapter
from app.adapters.campus_france_egypt import CampusFranceEgyptAdapter
from app.adapters.uk_visa_egypt import UKVISAEgyptAdapter
from app.adapters.vfs_global_egypt import VFSGlobalEgyptAdapter
from app.adapters.fintiba_sperrkonto import FintibaSperrkontoAdapter
from app.adapters.czech_embassy_cairo import CzechEmbassyCairoAdapter
from app.adapters.spain_visa_egypt import SpainVisaEgyptAdapter
from app.adapters.italy_embassy_cairo import ItalyEmbassyCairoAdapter

# One <h2> section with a short requirements list and a processing-time sentence --
# enough for each single-record adapter's real extract_documents() to produce one
# document + one populated visa_requirements record (mirrors the happy-path fixtures
# already proven in test_egypt_adapters.py).
_SINGLE_RECORD_FIXTURE_HTML = """
<html><body><main>
  <h2>Student Visa Requirements</h2>
  <p>Applicants must provide proof of enrollment and sufficient funds.</p>
  <ul>
    <li>Valid passport</li>
    <li>University enrollment certificate</li>
    <li>Proof of funds: EUR 5000</li>
  </ul>
  <p>Processing time: 20-30 working days.</p>
</main></body></html>
"""

# VFS Global Egypt covers multiple destination countries per page.
_VFS_FIXTURE_HTML = """
<html><body><main>
  <h2>Italy Visa Applications</h2>
  <ul><li>Valid passport</li></ul>
  <p>Processing time: 10-15 working days.</p>
  <h2>Czech Republic Visa Applications</h2>
  <ul><li>Valid passport</li><li>Travel insurance</li></ul>
  <p>Processing time: 15-20 working days.</p>
</main></body></html>
"""

_SINGLE_RECORD_ADAPTER_CLASSES = [
    GermanEmbassyCairoAdapter,
    APSCairoAdapter,
    CampusFranceEgyptAdapter,
    UKVISAEgyptAdapter,
    FintibaSperrkontoAdapter,
    CzechEmbassyCairoAdapter,
    SpainVisaEgyptAdapter,
    ItalyEmbassyCairoAdapter,
]

_ORIGINAL_6_ADAPTER_CLASS_NAMES = [
    "IELTSOrgAdapter", "DAADAdapter", "CheveningAdapter",
    "StudyInPolandAdapter", "StipendiumHungaricumAdapter", "MastersPortalAdapter",
]


def _build_real_scrape_results():
    """Runs each of the 9 Egypt adapters' REAL extract_documents() against fixture
    HTML, returning {class_name: real scrape()-shaped output}. Built fresh per test
    (not cached at module scope) since the wiring code mutates these dicts in place
    (pop("visa_requirements")) as it consumes them."""
    results = {}
    for adapter_cls in _SINGLE_RECORD_ADAPTER_CLASSES:
        adapter = adapter_cls()
        results[adapter_cls.__name__] = adapter.extract_documents(
            _SINGLE_RECORD_FIXTURE_HTML, url=adapter.target_url
        )
    vfs_adapter = VFSGlobalEgyptAdapter()
    results["VFSGlobalEgyptAdapter"] = vfs_adapter.extract_documents(
        _VFS_FIXTURE_HTML, url=vfs_adapter.target_url
    )
    return results


def _mock_original_6_as_noop(mocker, module_prefix: str):
    for class_name in _ORIGINAL_6_ADAPTER_CLASS_NAMES:
        mocker.patch(f"{module_prefix}.{class_name}.scrape", return_value=[])


def _mock_egypt_adapters_with_real_output(mocker, module_prefix: str, scrape_results: dict):
    for class_name, result in scrape_results.items():
        mocker.patch(f"{module_prefix}.{class_name}.scrape", return_value=result)


# ---------------------------------------------------------------------------
# handler.py (Lambda-style entry point)
# ---------------------------------------------------------------------------

def test_all_9_egypt_adapters_produce_documents_and_visa_requirements_via_handler(mocker):
    from handler import handle_ingestion

    _mock_original_6_as_noop(mocker, "handler")
    scrape_results = _build_real_scrape_results()
    _mock_egypt_adapters_with_real_output(mocker, "handler", scrape_results)

    mocker.patch("handler.generate_embeddings", return_value=[[0.0] * 1536] * 9)
    mock_upsert_chunks = mocker.patch("handler.upsert_chunks", return_value=True)
    mocker.patch("handler.check_existing_chunks", return_value=[])
    mock_upsert_visa = mocker.patch("handler.upsert_visa_requirement", return_value=True)

    result = handle_ingestion({"dry_run": False})

    # 8 single-record adapters -> 8 documents; VFS contributes 1 more document
    # (its multi-country page is still a single chunk-shaped document dict).
    assert result["processed_documents"] == 9
    assert mock_upsert_chunks.call_count == 1

    # 8 single-record adapters -> 8 visa records; VFS contributes 2 (Italy + Czech).
    assert mock_upsert_visa.call_count == 10
    assert result["visa_requirements_upserted"] == 10
    assert result["visa_requirements_failed"] == 0

    upserted_issuing_bodies = {call.args[0]["issuing_body"] for call in mock_upsert_visa.call_args_list}
    assert "German Embassy Cairo" in upserted_issuing_bodies
    assert "APS Cairo" in upserted_issuing_bodies
    assert "Campus France Egypt" in upserted_issuing_bodies
    assert "UK Visas and Immigration (UKVI)" in upserted_issuing_bodies
    assert "Fintiba GmbH" in upserted_issuing_bodies
    assert "Embassy of the Czech Republic in Cairo" in upserted_issuing_bodies
    assert "Consulate General of Spain in Cairo" in upserted_issuing_bodies
    assert "Italian Embassy Cairo" in upserted_issuing_bodies
    assert "VFS Global Egypt" in upserted_issuing_bodies

    vfs_countries = {
        call.args[0]["country"] for call in mock_upsert_visa.call_args_list
        if call.args[0]["issuing_body"] == "VFS Global Egypt"
    }
    assert vfs_countries == {"Italy", "Czech Republic"}


def test_document_chunk_upsert_failure_does_not_block_visa_upserts(mocker):
    """The 'vice versa' direction of the dual-write partial-failure check: a failure in
    the document-chunk upsert must not prevent the visa_requirements upserts, which run
    first and independently in handler.py's pipeline."""
    from handler import handle_ingestion

    _mock_original_6_as_noop(mocker, "handler")
    scrape_results = _build_real_scrape_results()
    _mock_egypt_adapters_with_real_output(mocker, "handler", scrape_results)

    mocker.patch("handler.generate_embeddings", return_value=[[0.0] * 1536] * 9)
    mocker.patch("handler.check_existing_chunks", return_value=[])
    mock_upsert_visa = mocker.patch("handler.upsert_visa_requirement", return_value=True)
    mocker.patch("handler.upsert_chunks", side_effect=Exception("RAG documents endpoint unavailable"))

    with pytest.raises(Exception, match="RAG documents endpoint unavailable"):
        handle_ingestion({"dry_run": False})

    # All 10 visa records were upserted before the chunk-upsert failure occurred.
    assert mock_upsert_visa.call_count == 10


# ---------------------------------------------------------------------------
# app/services/run_orchestrator.py (async orchestrator entry point)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_9_egypt_adapters_produce_documents_and_visa_requirements_via_orchestrator(mocker):
    from app.services.run_orchestrator import run_ingestion

    module = "app.services.run_orchestrator"
    _mock_original_6_as_noop(mocker, module)
    scrape_results = _build_real_scrape_results()
    _mock_egypt_adapters_with_real_output(mocker, module, scrape_results)

    mock_upsert_visa = mocker.patch(f"{module}.upsert_visa_requirement", return_value=True)
    upload_mock = mocker.patch(f"{module}.upload_report_to_s3")

    await run_ingestion()

    assert mock_upsert_visa.call_count == 10

    report_payload = upload_mock.call_args[0][1]
    assert report_payload["visa_requirements_upserted"] == 10
    assert report_payload["visa_requirements_failed"] == 0

    egypt_source_names = {
        "german_embassy_cairo", "aps_cairo", "campus_france_egypt", "uk_visa_egypt",
        "vfs_global_egypt", "fintiba_sperrkonto", "czech_embassy_cairo",
        "spain_visa_egypt", "italy_embassy_cairo",
    }
    sources_by_name = {s["name"]: s for s in report_payload["sources"]}
    assert egypt_source_names.issubset(sources_by_name.keys())
    for name in egypt_source_names:
        assert sources_by_name[name]["docs_processed"] == 1
        assert sources_by_name[name]["docs_failed"] == 0
