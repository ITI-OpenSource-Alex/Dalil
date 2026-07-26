"""BUG-010a regression: a blocked source must not look like an empty catalog.

DAAD was returning 403 to every request for an entire sprint. Playwright does not
raise on a 4xx -- page.goto() hands back the block page's body -- so extract_urls()
found no links, the adapter returned zero documents, and the run summary said
"status": "success", "scholarship_programs_upserted": 0. Nothing in the pipeline
could tell that apart from a source that genuinely had nothing new.

These tests pin the two halves of the fix: the fetch fails loudly, and the summary
carries the failure instead of swallowing it.
"""
import pytest

import handler
from app.core.retry import PageFetchError, is_transient_playwright_error


# ---------------------------------------------------------------------------
# Half 1: an HTTP error status raises rather than returning the error page body
# ---------------------------------------------------------------------------

def test_page_fetch_error_carries_url_and_status():
    err = PageFetchError("https://www2.daad.de/x", 403)

    assert err.status_code == 403
    assert "403" in str(err)
    assert "www2.daad.de" in str(err)


def test_permanent_status_is_not_retried():
    """A 403/404 is a settled answer -- retrying it three times with backoff only
    slows the run and makes the log noisier."""
    assert is_transient_playwright_error(PageFetchError("u", 403)) is False
    assert is_transient_playwright_error(PageFetchError("u", 404)) is False


def test_rate_limited_and_server_errors_are_still_retried():
    assert is_transient_playwright_error(PageFetchError("u", 429)) is True
    assert is_transient_playwright_error(PageFetchError("u", 503)) is True


# ---------------------------------------------------------------------------
# Half 2: the summary distinguishes "blocked" from "nothing new"
# ---------------------------------------------------------------------------

def test_summary_reports_adapter_failure_and_degrades_status(monkeypatch):
    async def fake_fetch(only=None, tier=2):
        return ([], [], [], [], {}, {"daad": "PageFetchError: HTTP 403 fetching https://www2.daad.de/x"})

    monkeypatch.setattr(handler, "fetch_all_adapters", fake_fetch)
    monkeypatch.setattr(handler, "write_completion_report", lambda summary: None)

    summary = handler.handle_ingestion({"dry_run": True})

    assert summary["status"] == "degraded"
    assert "daad" in summary["adapter_failures"]
    assert "403" in summary["adapter_failures"]["daad"]


def test_clean_run_is_still_success_with_no_failures(monkeypatch):
    """The degraded status must be driven by real failures only -- a healthy run
    that legitimately found nothing new stays green."""
    async def fake_fetch(only=None, tier=2):
        return ([], [], [], [], {}, {})

    monkeypatch.setattr(handler, "fetch_all_adapters", fake_fetch)
    monkeypatch.setattr(handler, "write_completion_report", lambda summary: None)

    summary = handler.handle_ingestion({"dry_run": True})

    assert summary["status"] == "success"
    assert summary["adapter_failures"] == {}


@pytest.mark.asyncio
async def test_fetch_all_adapters_records_failure_without_aborting_the_run(mocker):
    """Adapter isolation must survive: one blocked source cannot take down the
    others, but it must be named in the result rather than silently dropped."""
    def stub(source_name, scrape):
        adapter = mocker.Mock()
        adapter.source_name = source_name
        adapter.scrape = scrape
        return adapter

    blocked = stub(
        "daad",
        mocker.AsyncMock(side_effect=PageFetchError("https://www2.daad.de/x", 403)),
    )
    good = stub(
        "chevening",
        mocker.AsyncMock(return_value=[{"content": "real page", "url": "u"}]),
    )

    # Every adapter class is patched so the real ones never run, but each keeps a
    # distinct source_name -- otherwise the `only` filter below matches several
    # stubs at once and the document count stops meaning anything.
    mocker.patch("handler.DAADAdapter", return_value=blocked)
    mocker.patch("handler.CheveningAdapter", return_value=good)
    for cls, name in [
        ("IELTSOrgAdapter", "ielts_org"),
        ("StudyInPolandAdapter", "study_in_poland"),
        ("StipendiumHungaricumAdapter", "stipendium_hungaricum"),
        ("MastersPortalAdapter", "masters_portal"),
        ("VisaSourceAdapter", "visa_source"),
    ]:
        mocker.patch(f"handler.{cls}", return_value=stub(name, mocker.AsyncMock(return_value=[])))

    docs, _visa, _prog, _schol, _telemetry, failures = await handler.fetch_all_adapters(
        only=["daad", "chevening"]
    )

    assert "daad" in failures
    assert "403" in failures["daad"]
    # The healthy adapter still produced its document.
    assert len(docs) == 1


# ---------------------------------------------------------------------------
# BUG-014: a typo in INGESTION_ADAPTERS must not look like a healthy no-op run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_adapter_name_raises_instead_of_matching_nothing():
    """`INGESTION_ADAPTERS=visa_source` (the real name is `visa_adapter`) filtered
    every adapter out and reported success over zero sources -- costing a whole
    verification pass before anyone noticed the corpus had no visa content."""
    with pytest.raises(ValueError) as exc:
        await handler.fetch_all_adapters(only=["visa_source"])

    assert "visa_source" in str(exc.value)
    # The message must name the real options, or the next person repeats the typo.
    assert "visa_adapter" in str(exc.value)


@pytest.mark.asyncio
async def test_known_adapter_names_are_still_accepted(mocker):
    stub = mocker.Mock()
    stub.source_name = "daad"
    stub.scrape = mocker.AsyncMock(return_value=[])
    mocker.patch("handler.DAADAdapter", return_value=stub)

    docs, *_ = await handler.fetch_all_adapters(only=["daad"])

    assert docs == []
