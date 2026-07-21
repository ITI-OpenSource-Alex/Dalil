import pytest
import logging
from handler import handle_ingestion
from chunker import chunk_documents
from adapters import TestFixtureAdapter

def test_dry_run_logging_only(mocker):
    """
    Verify that in dry-run mode, the handler scrapes the 10 documents
    and logs exactly 10 would-upsert messages, without calling any external APIs.
    """
    # Mock embedding generator, RAG check-existing, and RAG upsert
    mock_embed = mocker.patch("handler.generate_embeddings")
    mock_check = mocker.patch("handler.check_existing_chunks")
    mock_upsert = mocker.patch("handler.upsert_chunks")
    
    # Mock the adapters fetch to just return the 10 fixture documents (no visa records)
    from langchain_core.documents import Document
    fixture_docs = [Document(page_content=f"Doc {i}", metadata={"id": f"id_{i}"}) for i in range(10)]
    async def mock_fetch(): return fixture_docs, []
    mocker.patch("handler.fetch_all_adapters", side_effect=mock_fetch)

    # Spy on the handler logger
    spy_logger = mocker.spy(logging.getLogger("ingestion_worker.handler"), "info")

    # Run the handler with dry_run enabled
    event = {"dry_run": True}
    result = handle_ingestion(event)

    # Verify returned counts matching the 10 documents in the fixture
    assert result["dry_run"] is True
    assert result["processed_documents"] == 10
    assert result["total_chunks"] == 10
    assert result["new_chunks_upserted"] == 0
    assert result["skipped_chunks"] == 10
    assert result["visa_requirements_upserted"] == 0
    assert result["visa_requirements_failed"] == 0

    # Verify no external APIs were hit
    mock_embed.assert_not_called()
    mock_check.assert_not_called()
    mock_upsert.assert_not_called()
    
    # Verify exactly 10 log messages stating what "Would upsert"
    would_upsert_logs = [
        call for call in spy_logger.call_args_list 
        if "Would upsert chunk ID" in call[0][0]
    ]
    assert len(would_upsert_logs) == 10

def test_idempotency_skips_embedding_api_calls(mocker):
    """
    Verify that running ingestion twice with the same documents
    causes the second run to completely skip OpenAI embedding generation
    and RAG upserts by querying check_existing_chunks first.
    """
    # Mock RAG upsert and OpenAI embedding generator (returning mock 1536-dim vectors)
    mock_embed = mocker.patch("handler.generate_embeddings", return_value=[[0.0]*1536]*10)
    mock_upsert = mocker.patch("handler.upsert_chunks", return_value=True)
    
    # Mock the adapters fetch (no visa records)
    from langchain_core.documents import Document
    fixture_docs = [Document(page_content=f"Doc {i}", metadata={"id": f"id_{i}", "source_url": "test"}) for i in range(10)]
    async def mock_fetch(): return fixture_docs, []
    mocker.patch("handler.fetch_all_adapters", side_effect=mock_fetch)
    
    # FIRST RUN: Mock check-existing to indicate no chunks exist in DB (first time run)
    mocker.patch("handler.check_existing_chunks", return_value=[])
    
    event = {"dry_run": False}
    result_first = handle_ingestion(event)
    
    # Verify first run processed and upserted all 10 chunks
    assert result_first["new_chunks_upserted"] == 10
    assert result_first["skipped_chunks"] == 0
    assert mock_embed.call_count == 1
    assert mock_upsert.call_count == 1
    
    # Reset call counts on the mocks
    mock_embed.reset_mock()
    mock_upsert.reset_mock()
    
    # SECOND RUN: Mock check-existing to return all chunk IDs as already existing
    chunks = chunk_documents(fixture_docs)
    existing_chunk_ids = [c.metadata["id"] for c in chunks]
    
    mocker.patch("handler.check_existing_chunks", return_value=existing_chunk_ids)
    
    result_second = handle_ingestion(event)
    
    # Verify second run did not generate embeddings or upsert anything
    assert result_second["new_chunks_upserted"] == 0
    assert result_second["skipped_chunks"] == 10
    mock_embed.assert_not_called()
    mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Task 16: dual-write of structured visa_requirements records
# ---------------------------------------------------------------------------

def test_visa_requirements_upserted_independently_of_document_pipeline(mocker):
    """
    Verify that structured visa_requirements records returned by fetch_all_adapters are
    upserted via client.upsert_visa_requirement, once per record, independently of the
    document chunk pipeline (GOA-086 Task 16 dual-write).
    """
    mocker.patch("handler.generate_embeddings", return_value=[[0.0] * 1536] * 2)
    mock_upsert_chunks = mocker.patch("handler.upsert_chunks", return_value=True)
    mock_upsert_visa = mocker.patch("handler.upsert_visa_requirement", return_value=True)
    mocker.patch("handler.check_existing_chunks", return_value=[])

    from langchain_core.documents import Document
    fixture_docs = [Document(page_content=f"Doc {i}", metadata={"id": f"id_{i}", "source_url": "test"}) for i in range(2)]
    visa_records = [
        {"country": "Germany", "visa_type": "Student Visa", "issuing_body": "German Embassy Cairo"},
        {"country": "France", "visa_type": "Student Visa", "issuing_body": "Campus France Egypt"},
    ]
    async def mock_fetch(): return fixture_docs, visa_records
    mocker.patch("handler.fetch_all_adapters", side_effect=mock_fetch)

    event = {"dry_run": False}
    result = handle_ingestion(event)

    assert mock_upsert_visa.call_count == 2
    mock_upsert_visa.assert_any_call(visa_records[0])
    mock_upsert_visa.assert_any_call(visa_records[1])
    assert result["visa_requirements_upserted"] == 2
    assert result["visa_requirements_failed"] == 0
    # Document pipeline still ran normally alongside the visa upserts.
    assert mock_upsert_chunks.call_count == 1
    assert result["new_chunks_upserted"] == 2


def test_visa_requirement_failure_does_not_block_others_or_document_pipeline(mocker):
    """
    Verify that a failure upserting one visa_requirements record doesn't prevent the
    remaining records from being attempted, and doesn't block the document chunk
    pipeline from completing (GOA-086 Task 16 failure isolation).
    """
    mocker.patch("handler.generate_embeddings", return_value=[[0.0] * 1536] * 2)
    mock_upsert_chunks = mocker.patch("handler.upsert_chunks", return_value=True)
    mocker.patch("handler.check_existing_chunks", return_value=[])

    visa_records = [
        {"country": "Germany", "visa_type": "Student Visa", "issuing_body": "German Embassy Cairo"},
        {"country": "France", "visa_type": "Student Visa", "issuing_body": "Campus France Egypt"},
    ]
    mock_upsert_visa = mocker.patch(
        "handler.upsert_visa_requirement",
        side_effect=[Exception("RAG service unavailable"), True]
    )

    from langchain_core.documents import Document
    fixture_docs = [Document(page_content=f"Doc {i}", metadata={"id": f"id_{i}", "source_url": "test"}) for i in range(2)]
    async def mock_fetch(): return fixture_docs, visa_records
    mocker.patch("handler.fetch_all_adapters", side_effect=mock_fetch)

    event = {"dry_run": False}
    result = handle_ingestion(event)

    assert mock_upsert_visa.call_count == 2
    assert result["visa_requirements_upserted"] == 1
    assert result["visa_requirements_failed"] == 1
    # Document pipeline still completed despite the visa upsert failure.
    assert mock_upsert_chunks.call_count == 1
    assert result["new_chunks_upserted"] == 2


def test_dry_run_logs_visa_requirements_without_upserting(mocker):
    """Verify dry-run mode logs would-upsert messages for visa records without calling
    the real upsert function."""
    mock_upsert_visa = mocker.patch("handler.upsert_visa_requirement")
    mocker.patch("handler.generate_embeddings")
    mocker.patch("handler.check_existing_chunks")
    mocker.patch("handler.upsert_chunks")

    visa_records = [
        {"country": "Germany", "visa_type": "Student Visa", "issuing_body": "German Embassy Cairo"},
    ]
    from langchain_core.documents import Document
    fixture_docs = [Document(page_content="Doc 0", metadata={"id": "id_0"})]
    async def mock_fetch(): return fixture_docs, visa_records
    mocker.patch("handler.fetch_all_adapters", side_effect=mock_fetch)

    spy_logger = mocker.spy(logging.getLogger("ingestion_worker.handler"), "info")

    event = {"dry_run": True}
    result = handle_ingestion(event)

    assert result["visa_requirements_upserted"] == 0
    assert result["visa_requirements_failed"] == 0
    mock_upsert_visa.assert_not_called()

    would_upsert_visa_logs = [
        call for call in spy_logger.call_args_list
        if "Would upsert visa requirement" in call[0][0]
    ]
    assert len(would_upsert_visa_logs) == 1