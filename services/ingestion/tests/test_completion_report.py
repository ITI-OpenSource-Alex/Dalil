"""ING-04 (BUG-009): the completion report is the run's observable outcome.

The original criterion asserted on a Prometheus counter. That was unmeetable
twice over: the counter is only touched by the canonical runner, which nothing but
its own unit test calls, and ingestion is a run-to-completion container with no
HTTP server, so an in-process counter can never be scraped. The completion report
carries strictly more than the counter would, so it is what ING-04 now asserts on.

These tests pin the report's *contents*. A report that writes successfully but
omits the fields an operator needs is the same class of failure as a green run
over zero rows.
"""
import json

import pytest

import handler

# The keys ING-04 requires. Losing any of these silently would leave an operator
# unable to tell a healthy run from a blocked one -- which is how BUG-008 and
# BUG-010a both went unnoticed for a sprint.
REQUIRED_KEYS = {
    "status",
    "processed_documents",
    "total_chunks",
    "new_chunks_upserted",
    "skipped_chunks",
    "docs_skipped_at_source",
    "source_telemetry",
    "adapter_failures",
    "scholarship_programs_upserted",
    "program_requirements_upserted",
    "visa_requirements_upserted",
}


class _FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


@pytest.fixture
def fake_s3(monkeypatch):
    client = _FakeS3()
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: client)
    return client


def test_report_body_is_valid_json_carrying_every_required_field(fake_s3):
    summary = {
        "status": "success",
        "dry_run": False,
        "processed_documents": 3,
        "total_chunks": 45,
        "new_chunks_upserted": 0,
        "skipped_chunks": 45,
        "visa_requirements_upserted": 0,
        "program_requirements_upserted": 0,
        "scholarship_programs_upserted": 2,
        "docs_skipped_at_source": 2739,
        "source_telemetry": {"masters_portal": {"cs": {"skipped": 2739}}},
        "adapter_failures": {},
    }

    key = handler.write_completion_report(summary)

    assert key and key.startswith("reports/")
    assert len(fake_s3.puts) == 1
    body = json.loads(fake_s3.puts[0]["Body"].decode("utf-8"))
    assert REQUIRED_KEYS <= set(body)
    assert body["docs_skipped_at_source"] == 2739
    assert body["scholarship_programs_upserted"] == 2


def test_report_records_a_blocked_source_rather_than_hiding_it(fake_s3):
    """A run where a source was blocked must be legible as such from the report
    alone -- the operator does not have the container logs a week later."""
    summary = {
        "status": "degraded",
        "dry_run": False,
        "processed_documents": 0,
        "total_chunks": 0,
        "new_chunks_upserted": 0,
        "skipped_chunks": 0,
        "visa_requirements_upserted": 0,
        "program_requirements_upserted": 0,
        "scholarship_programs_upserted": 0,
        "docs_skipped_at_source": 0,
        "source_telemetry": {"daad": {}},
        "adapter_failures": {"daad": "PageFetchError: HTTP 403 fetching https://www2.daad.de/x"},
    }

    handler.write_completion_report(summary)

    body = json.loads(fake_s3.puts[0]["Body"].decode("utf-8"))
    assert body["status"] == "degraded"
    assert "403" in body["adapter_failures"]["daad"]


def test_dry_run_writes_no_report(fake_s3):
    """A rehearsal that leaves artefacts behind is not a rehearsal (BUG-001)."""
    assert handler.write_completion_report({"dry_run": True, "status": "success"}) is None
    assert fake_s3.puts == []


def test_reporting_failure_is_visible_to_the_platform(monkeypatch):
    """The report is the durable scheduled-run artifact, so losing it is a failure."""
    import boto3

    def explode(*a, **k):
        raise RuntimeError("S3 unavailable")

    monkeypatch.setattr(boto3, "client", explode)

    with pytest.raises(handler.CompletionReportError):
        handler.write_completion_report({"dry_run": False, "status": "success"})
