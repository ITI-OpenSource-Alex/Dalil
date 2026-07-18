import pytest
from app.services.run_orchestrator import run_ingestion

# The 7 GOA-086 Egypt visa adapters, mocked to a neutral no-op ([]) in tests that only
# care about the original 6 adapters' behavior, so no real network calls are attempted.
_EGYPT_ADAPTER_CLASSES = [
    "VisaSourceAdapter"
]


def _mock_egypt_adapters_as_noop(mocker):
    for class_name in _EGYPT_ADAPTER_CLASSES:
        mocker.patch(f"app.services.run_orchestrator.{class_name}.scrape", return_value=[])


@pytest.mark.asyncio
async def test_one_adapter_failure_does_not_crash_run(mocker):
    # 1. Arrange: Mock the 6 original adapters
    mocker.patch("app.services.run_orchestrator.IELTSOrgAdapter.scrape", return_value=[{"content": "success", "source": "ielts_org"}])
    mocker.patch("app.services.run_orchestrator.DAADAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.CheveningAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StudyInPolandAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StipendiumHungaricumAdapter.scrape", return_value=[])

    # Force MastersPortal to throw a catastrophic error
    mocker.patch("app.services.run_orchestrator.MastersPortalAdapter.scrape", side_effect=Exception("Playwright crashed!"))

    # Mock the 9 GOA-086 Egypt adapters as no-ops so this test stays focused on the
    # original 6 adapters and doesn't hit real network calls.
    _mock_egypt_adapters_as_noop(mocker)

    # Mock the S3 upload so we don't actually hit LocalStack during tests
    upload_mock = mocker.patch("app.services.run_orchestrator.upload_report_to_s3")

    # 2. Act: Run the orchestrator
    # Because we used return_exceptions=True, this should NOT throw an exception!
    await run_ingestion()

    # 3. Assert: Verify the S3 report was still uploaded with the other successes
    upload_mock.assert_called_once()

    # Verify the failure was recorded in the report payload
    call_args = upload_mock.call_args[0]
    report_payload = call_args[1]

    # Find MastersPortal in the report sources
    masters_portal_report = next((s for s in report_payload["sources"] if s["name"] == "masters_portal"), None)
    assert masters_portal_report is not None
    assert masters_portal_report["docs_failed"] == 1
    assert masters_portal_report["docs_processed"] == 0

@pytest.mark.asyncio
async def test_failure_ratio_over_10pct_logs_error(mocker):
    # 1. Arrange: Mock one success and one failure to create a 50% failure ratio
    mocker.patch("app.services.run_orchestrator.IELTSOrgAdapter.scrape", return_value=[{"content": "success", "source": "ielts_org"}])
    mocker.patch("app.services.run_orchestrator.DAADAdapter.scrape", side_effect=Exception("Network error"))
    mocker.patch("app.services.run_orchestrator.CheveningAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StudyInPolandAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StipendiumHungaricumAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.MastersPortalAdapter.scrape", return_value=[])

    _mock_egypt_adapters_as_noop(mocker)

    mocker.patch("app.services.run_orchestrator.upload_report_to_s3")

    # Spy on the logger
    logger_spy = mocker.patch("app.services.run_orchestrator.logger.error")

    # 2. Act
    await run_ingestion()

    # 3. Assert: Check if the 'high_failure_ratio_alarm' was logged
    logger_spy.assert_any_call("high_failure_ratio_alarm", ratio=0.5, threshold=0.1)


# ---------------------------------------------------------------------------
# Task 16: dual-write of structured visa_requirements records
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_visa_requirements_are_upserted_once_per_record(mocker):
    """Mocks two Egypt adapters returning populated visa_requirements and asserts
    client.upsert_visa_requirement is called once per accumulated record across the run."""
    mocker.patch("app.services.run_orchestrator.IELTSOrgAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.DAADAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.CheveningAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StudyInPolandAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StipendiumHungaricumAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.MastersPortalAdapter.scrape", return_value=[])

    german_record = {"country": "Germany", "visa_type": "Student Visa", "issuing_body": "German Embassy Cairo"}
    campus_france_record = {"country": "France", "visa_type": "Student Visa", "issuing_body": "Campus France Egypt"}
    mocker.patch(
        "app.services.run_orchestrator.VisaSourceAdapter.scrape",
        return_value=[
            {"content": "German visa info", "source": "german_embassy_cairo", "visa_requirements": [german_record]},
            {"content": "Campus France info", "source": "campus_france_egypt", "visa_requirements": [campus_france_record]}
        ],
    )

    mock_upsert_visa = mocker.patch("app.services.run_orchestrator.upsert_visa_requirement", return_value=True)
    upload_mock = mocker.patch("app.services.run_orchestrator.upload_report_to_s3")

    await run_ingestion()

    assert mock_upsert_visa.call_count == 2
    mock_upsert_visa.assert_any_call(german_record)
    mock_upsert_visa.assert_any_call(campus_france_record)

    report_payload = upload_mock.call_args[0][1]
    assert report_payload["visa_requirements_upserted"] == 2
    assert report_payload["visa_requirements_failed"] == 0


@pytest.mark.asyncio
async def test_visa_requirement_failure_does_not_block_other_records_or_document_pipeline(mocker):
    """A failure upserting one visa_requirements record must not prevent other records
    from being attempted, nor prevent the Document from still being built for that page."""
    mocker.patch("app.services.run_orchestrator.IELTSOrgAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.DAADAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.CheveningAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StudyInPolandAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StipendiumHungaricumAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.MastersPortalAdapter.scrape", return_value=[])

    failing_record = {"country": "Germany", "visa_type": "Student Visa", "issuing_body": "German Embassy Cairo"}
    succeeding_record = {"country": "France", "visa_type": "Student Visa", "issuing_body": "Campus France Egypt"}
    mocker.patch(
        "app.services.run_orchestrator.VisaSourceAdapter.scrape",
        return_value=[
            {"content": "German visa info", "source": "german_embassy_cairo", "visa_requirements": [failing_record]},
            {"content": "Campus France info", "source": "campus_france_egypt", "visa_requirements": [succeeding_record]}
        ],
    )

    mock_upsert_visa = mocker.patch(
        "app.services.run_orchestrator.upsert_visa_requirement",
        side_effect=[Exception("RAG service unavailable"), True],
    )
    upload_mock = mocker.patch("app.services.run_orchestrator.upload_report_to_s3")

    await run_ingestion()

    # Both records were attempted despite the first one failing.
    assert mock_upsert_visa.call_count == 2

    report_payload = upload_mock.call_args[0][1]
    assert report_payload["visa_requirements_upserted"] == 1
    assert report_payload["visa_requirements_failed"] == 1

    # The document for the page whose visa upsert failed was still processed.
    # GOA-116 note: one generic VisaSourceAdapter now covers every visa source, so both
    # pages report under a single adapter entry — docs_processed is 2, not the 1-per-page
    # of the pre-GOA-116 world where each embassy had its own adapter class. What this
    # assertion guards is unchanged: the failed upsert did not stop either Document from
    # being built (dual-write isolation).
    visa_source_entry = next(
        (s for s in report_payload["sources"] if s["name"] == "visa_adapter"), None
    )
    assert visa_source_entry is not None
    assert visa_source_entry["docs_processed"] == 2
    assert visa_source_entry["docs_failed"] == 0
