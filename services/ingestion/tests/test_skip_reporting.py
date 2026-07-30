"""BUG-008: the run summary must report skips that happen at the SOURCE.

Already-ingested cards are filtered by `is_url_scraped` inside the adapter, before
chunking. The summary only ever counted chunk-level skips, so a replay that correctly
skipped 986 of 1000 cards reported `skipped_chunks: 0` — the exact field ING-03 tells an
operator to check. That produced a false "idempotency is broken" diagnosis during the
GOA-101 verification run. The number existed all along; it died in a log line.
"""

import handler


class _Adapter:
    def __init__(self, name, telemetry):
        self.source_name = name
        self.last_run_telemetry = telemetry


def test_summary_reports_source_level_skips(monkeypatch):
    telemetry = {
        "masters_portal": {
            "engineering": {"discovered": 1031, "skipped": 2739, "extracted": 1, "failed": 0},
            "computer_science": {"discovered": 0, "skipped": 0, "extracted": 0, "failed": 0},
        }
    }

    async def fake_fetch(only=None, tier=2):
        return [], [], [], [], telemetry

    monkeypatch.setattr(handler, "fetch_all_adapters", fake_fetch)
    monkeypatch.setattr(handler, "check_existing_chunks", lambda ids: [])
    monkeypatch.setattr(handler, "write_completion_report", lambda summary: None)

    summary = handler.handle_ingestion({})

    assert summary["docs_skipped_at_source"] == 2739, (
        "a run that skipped 2739 already-ingested cards must say so; reporting only "
        "chunk-level skips is what made idempotency look broken"
    )
    assert summary["source_telemetry"] == telemetry


def test_dry_run_also_reports_source_skips(monkeypatch):
    """A dry run is the cheapest way to ask 'what would this do' — it has to answer."""
    telemetry = {"masters_portal": {"engineering": {"skipped": 12}}}

    async def fake_fetch(only=None, tier=2):
        return [], [], [], [], telemetry

    monkeypatch.setattr(handler, "fetch_all_adapters", fake_fetch)
    summary = handler.handle_ingestion({"dry_run": True})

    assert summary["dry_run"] is True
    assert summary["docs_skipped_at_source"] == 12


def test_missing_telemetry_is_zero_not_a_crash(monkeypatch):
    """Adapters without Tier 1 telemetry (visa, ielts_org) must not break the summary."""
    async def fake_fetch(only=None, tier=2):
        return [], [], [], [], {"visa_adapter": {}}

    monkeypatch.setattr(handler, "fetch_all_adapters", fake_fetch)
    monkeypatch.setattr(handler, "check_existing_chunks", lambda ids: [])
    monkeypatch.setattr(handler, "write_completion_report", lambda summary: None)

    assert handler.handle_ingestion({})["docs_skipped_at_source"] == 0
