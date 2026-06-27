import logging
from config import settings
from adapters import TestFixtureAdapter
from chunker import chunk_documents
from embedder import generate_embeddings
from client import check_existing_chunks, upsert_chunks


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingestion_worker.handler")

def handle_ingestion(event: dict, context=None) -> dict:
    """
    Lambda-compatible entry point for the ingestion worker.
    Ties together scraping, chunking, idempotency verification, embedding generation,
    and bulk upserting to the RAG service.
    """
    logger.info("Ingestion pipeline started with event: %s", event)
    # Allow overriding dry_run and url via the lambda trigger event
    url = event.get("url", "https://goa.app/test-fixture")
    dry_run = event.get("dry_run", settings.dry_run)
    # 1. Scrape documents using the fixture adapter (scaffolded)
    adapter = TestFixtureAdapter()
    logger.info("Scraping source URL: %s", url)
    documents = adapter.scrape(url)
    logger.info("Scraped %d source documents", len(documents))
    # 2. Chunk documents and assign deterministic UUID v5 IDs
    chunks = chunk_documents(documents)
    logger.info("Generated %d token-based chunks", len(chunks))
    # 3. Handle DryRun Mode
    if dry_run:
        logger.info("Ingestion running in DRY-RUN mode. No changes will be written.")
        for chunk in chunks:
            logger.info(
                "Would upsert chunk ID %s from source %s: [Content preview: %s...]",
                chunk.metadata["id"],
                chunk.metadata.get("source_url"),
                chunk.page_content[:60].replace("\n", " ")
            )
        return {
            "status": "success",
            "dry_run": True,
            "processed_documents": len(documents),
            "total_chunks": len(chunks),
            "new_chunks_upserted": 0,
            "skipped_chunks": len(chunks)
        }
    # 4. Check which chunks already exist in the database (Idempotency check)
    chunk_ids = [chunk.metadata["id"] for chunk in chunks]
    existing_ids = check_existing_chunks(chunk_ids)
    logger.info("Found %d existing chunk IDs in RAG database", len(existing_ids))
    # Filter out chunks that are already ingested
    new_chunks = [c for c in chunks if c.metadata["id"] not in existing_ids]
    logger.info("Identified %d new chunks that require embedding and upsert", len(new_chunks))
    if not new_chunks:
        logger.info("All chunks already exist in the database. Ingestion completed with 0 updates.")
        return {
            "status": "success",
            "dry_run": False,
            "processed_documents": len(documents),
            "total_chunks": len(chunks),
            "new_chunks_upserted": 0,
            "skipped_chunks": len(chunks)
        }
    # 5. Generate embeddings for the new chunks
    new_texts = [c.page_content for c in new_chunks]
    embeddings = generate_embeddings(new_texts)
    logger.info("Generated %d embeddings using OpenAI", len(embeddings))
    # 6. Map chunks to upsert schema payloads
    upsert_payload = []
    for chunk, embedding in zip(new_chunks, embeddings):
        upsert_payload.append({
            "id": chunk.metadata["id"],
            "content": chunk.page_content,
            "embedding": embedding,
            "source_url": chunk.metadata.get("source_url"),
            "category": chunk.metadata.get("category")
        })
    # 7. Upsert to RAG service
    upsert_chunks(upsert_payload)
    logger.info("Bulk upsert of %d chunks completed successfully", len(new_chunks))
    return {
        "status": "success",
        "dry_run": False,
        "processed_documents": len(documents),
        "total_chunks": len(chunks),
        "new_chunks_upserted": len(new_chunks),
        "skipped_chunks": len(chunks) - len(new_chunks)
    }