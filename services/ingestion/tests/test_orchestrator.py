import pytest
from app.services.run_orchestrator import run_ingestion

@pytest.mark.asyncio
async def test_one_adapter_failure_does_not_crash_run(mocker):
    # 1. Arrange: Mock the 6 adapters
    mocker.patch("app.services.run_orchestrator.IELTSOrgAdapter.scrape", return_value=[{"content": "success", "source": "ielts_org"}])
    mocker.patch("app.services.run_orchestrator.DAADAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.CheveningAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StudyInPolandAdapter.scrape", return_value=[])
    mocker.patch("app.services.run_orchestrator.StipendiumHungaricumAdapter.scrape", return_value=[])
    
    # Force MastersPortal to throw a catastrophic error
    mocker.patch("app.services.run_orchestrator.MastersPortalAdapter.scrape", side_effect=Exception("Playwright crashed!"))
    
    # Mock the S3 upload so we don't actually hit LocalStack during tests
    upload_mock = mocker.patch("app.services.run_orchestrator.upload_report_to_s3")

    # 2. Act: Run the orchestrator
    # Because we used return_exceptions=True, this should NOT throw an exception!
    await run_ingestion()

    # 3. Assert: Verify the S3 report was still uploaded with the other 5 successes
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
    
    mocker.patch("app.services.run_orchestrator.upload_report_to_s3")
    
    # Spy on the logger
    logger_spy = mocker.patch("app.services.run_orchestrator.logger.error")

    # 2. Act
    await run_ingestion()

    # 3. Assert: Check if the 'high_failure_ratio_alarm' was logged
    logger_spy.assert_any_call("high_failure_ratio_alarm", ratio=0.5, threshold=0.1)