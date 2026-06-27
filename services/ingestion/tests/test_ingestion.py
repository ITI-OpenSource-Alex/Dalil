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
    docs = TestFixtureAdapter().scrape("https://goa.app/test-fixture")
    chunks = chunk_documents(docs)
    existing_chunk_ids = [c.metadata["id"] for c in chunks]
    
    mocker.patch("handler.check_existing_chunks", return_value=existing_chunk_ids)
    
    result_second = handle_ingestion(event)
    
    # Verify second run did not generate embeddings or upsert anything
    assert result_second["new_chunks_upserted"] == 0
    assert result_second["skipped_chunks"] == 10
    mock_embed.assert_not_called()
    mock_upsert.assert_not_called()