import logging
import os
from config import settings
from adapters import TestFixtureAdapter
from chunker import chunk_documents
from embedder import generate_embeddings
from client import (
    check_existing_chunks,
    upsert_chunks,
    upsert_program_requirement,
    upsert_scholarship_program,
    upsert_visa_requirement,
)
from app.core.crawl_state import crawl_state


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingestion_worker.handler")

from app.adapters.ielts_org import IELTSOrgAdapter
from app.adapters.daad import DAADAdapter
from app.adapters.chevening import CheveningAdapter
from app.adapters.study_in_poland import StudyInPolandAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter
from app.adapters.masters_portal import MastersPortalAdapter
from app.adapters.visa_adapter import VisaSourceAdapter
import asyncio

async def fetch_all_adapters(only: list[str] | None = None, tier: int = 2):
    adapters = [
        IELTSOrgAdapter(), DAADAdapter(), CheveningAdapter(),
        StudyInPolandAdapter(), StipendiumHungaricumAdapter(), MastersPortalAdapter(),
        VisaSourceAdapter(),
    ]
    # Controlled runs (GOA-111 live verification, demos) can scope to specific
    # sources: event {"adapters": ["masters_portal"]} or INGESTION_ADAPTERS env.
    if only:
        known = {a.source_name for a in adapters}
        unknown = [name for name in only if name not in known]
        if unknown:
            # A name that matches nothing used to filter every adapter out and
            # report success over zero sources -- `visa_source` instead of
            # `visa_adapter` cost a full verification pass (BUG-014). A typo must
            # not be indistinguishable from a healthy no-op run.
            raise ValueError(
                f"Unknown adapter(s) in INGESTION_ADAPTERS: {', '.join(sorted(unknown))}. "
                f"Known sources: {', '.join(sorted(known))}"
            )
        adapters = [a for a in adapters if a.source_name in only]

    # Option B Tier 1: build the catalog from search-API cards with no page fetch.
    # INGESTION_TIER=1 (or event {"tier": 1}) selects it. Tier 2 remains the default
    # page-fetching path that enriches the document corpus for a prioritised subset.
    if tier == 1:
        adapters = [a for a in adapters if hasattr(a, "scrape_cards")]
        calls = [a.scrape_cards() for a in adapters]
    else:
        calls = [a.scrape() for a in adapters]

    from langchain_core.documents import Document

    for adapter in adapters:
        logger.info("Scraping source: %s (tier %d)", adapter.source_name, tier)

    # Scrape all adapters concurrently; return_exceptions=True isolates a single
    # adapter's failure so it can't abort the whole run (matches the isolation
    # pattern already used in app/services/run_orchestrator.py).
    results = await asyncio.gather(*calls, return_exceptions=True)

    all_docs = []
    all_visa_records = []
    all_program_records = []
    all_scholarship_records = []
    adapter_failures = {}
    for adapter, result in zip(adapters, results):
        if isinstance(result, Exception):
            logger.error("Adapter %s failed completely: %s", adapter.source_name, str(result))
            # Record it, don't just log it. A blocked source produces zero rows, and
            # zero rows on their own look exactly like a source that had nothing new
            # -- the summary has to distinguish the two or nobody notices for a
            # sprint (BUG-010a).
            adapter_failures[adapter.source_name] = f"{type(result).__name__}: {result}"
            continue
        for d in result:
            # Structured visa requirements (GOA-086) are upserted independently of the
            # document chunk pipeline below, so pop them out before they'd otherwise be
            # discarded here -- see GOA-086 implementation plan Task 16.
            all_program_records.extend(d.pop("program_requirements", []))
            all_scholarship_records.extend(d.pop("scholarship_programs", []))
            all_visa_records.extend(d.pop("visa_requirements", []))
            all_docs.append(Document(page_content=d['content'], metadata={'source_url': d.get('source_url') or d.get('url'), 'category': d.get('category')}))

    # Adapter-level skips are the ones that carry the idempotency signal — a card
    # already ingested never reaches the chunker, so counting only chunk-level skips
    # reports 0 for a run that skipped nearly everything.
    source_telemetry = {
        adapter.source_name: getattr(adapter, "last_run_telemetry", {}) or {}
        for adapter in adapters
    }
    return (all_docs, all_visa_records, all_program_records, all_scholarship_records,
            source_telemetry, adapter_failures)

INGESTION_REPORTS_BUCKET = os.getenv("INGESTION_REPORTS_BUCKET", "goa-ingestion-reports")


def write_completion_report(summary: dict) -> str | None:
    """Publish the run summary to S3 (ING-02). Returns the key, or None if not written.

    A reporting failure must never fail an otherwise-good ingestion run: the data is
    the product, the report is bookkeeping. Dry runs write nothing, by definition.
    """
    if summary.get("dry_run"):
        return None
    try:
        import datetime
        import json as _json

        import boto3

        key = f"reports/{datetime.datetime.utcnow().strftime('%Y-%m-%dT%H%M%SZ')}.json"
        client = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
        client.put_object(
            Bucket=INGESTION_REPORTS_BUCKET,
            Key=key,
            Body=_json.dumps(summary, indent=2, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Completion report written to s3://%s/%s", INGESTION_REPORTS_BUCKET, key)
        return key
    except Exception as e:
        logger.error("Could not write completion report: %s", e)
        return None


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
    # Controlled runs may scope to specific sources (GOA-111 live verification).
    only = event.get("adapters") or (
        [s.strip() for s in os.environ["INGESTION_ADAPTERS"].split(",") if s.strip()]
        if os.environ.get("INGESTION_ADAPTERS") else None
    )
    # Tier 1 (cards only, whole catalog, no browser) vs Tier 2 (page enrichment).
    tier = int(event.get("tier") or os.environ.get("INGESTION_TIER") or 2)
    # A dry run must be read-only from the FIRST network call, not from step 3. The
    # adapters mark crawl state as they scrape, so this has to be armed before
    # fetch_all_adapters, otherwise the rehearsal marks URLs done and the next real
    # run skips them.
    crawl_state.read_only = dry_run
    # 1. Scrape documents using the real adapters
    res = asyncio.run(fetch_all_adapters(only=only, tier=tier))
    documents, visa_records = res[0], res[1]
    program_records = res[2] if len(res) > 2 else []
    scholarship_records = res[3] if len(res) > 3 else []
    source_telemetry = res[4] if len(res) > 4 else {}
    adapter_failures = res[5] if len(res) > 5 else {}
    if adapter_failures:
        logger.error("Adapters that produced nothing due to failure: %s", adapter_failures)
    docs_skipped_at_source = sum(
        counts.get("skipped", 0)
        for per_discipline in source_telemetry.values()
        for counts in per_discipline.values()
    )
    logger.info("Skipped %d already-ingested items at the source", docs_skipped_at_source)
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
        for record in visa_records:
            logger.info(
                "Would upsert visa requirement: %s / %s / %s",
                record.get("country"), record.get("visa_type"), record.get("issuing_body")
            )
        for record in program_records:
            logger.info(
                "Would upsert program requirement: %s / %s",
                record.get("university"), record.get("program_name")
            )
        for record in scholarship_records:
            logger.info(
                "Would upsert scholarship program: %s",
                record.get("name")
            )
        return {
            "status": "degraded" if adapter_failures else "success",
            "dry_run": True,
            "processed_documents": len(documents),
            "total_chunks": len(chunks),
            "new_chunks_upserted": 0,
            "skipped_chunks": len(chunks),
            "visa_requirements_upserted": 0,
            "visa_requirements_failed": 0,
            "program_requirements_upserted": 0,
            "program_requirements_failed": 0,
            "scholarship_programs_upserted": 0,
            "scholarship_programs_failed": 0,
            "docs_skipped_at_source": docs_skipped_at_source,
            "source_telemetry": source_telemetry,
            "adapter_failures": adapter_failures,
        }
    # 4. Upsert structured records (visa, program, scholarship) independently of the document
    #    chunk pipeline below -- each record's success/failure is isolated so a failure
    #    on one side never blocks the other (dual-write strategy).
    visa_requirements_upserted = 0
    visa_requirements_failed = 0
    for record in visa_records:
        try:
            upsert_visa_requirement(record)
            visa_requirements_upserted += 1
        except Exception as e:
            logger.error(
                "Failed to upsert visa requirement (%s / %s): %s",
                record.get("issuing_body"), record.get("visa_type"), str(e)
            )
            visa_requirements_failed += 1

    program_requirements_upserted = 0
    program_requirements_failed = 0
    for record in program_records:
        try:
            upsert_program_requirement(record)
            program_requirements_upserted += 1
            # Promote crawl status to 'scraped' only after the RAG upsert succeeded —
            # the adapter left it at 'extracted', so a failure here gets retried next run.
            if record.get("source_url") and "mastersportal.com" in record["source_url"]:
                crawl_state.mark_url_status("masters_portal", "unknown", record["source_url"], "scraped")
        except Exception as e:
            logger.error(
                "Failed to upsert program requirement (%s / %s): %s",
                record.get("university"), record.get("program_name"), str(e)
            )
            program_requirements_failed += 1

    scholarship_programs_upserted = 0
    scholarship_programs_failed = 0
    for record in scholarship_records:
        try:
            upsert_scholarship_program(record)
            scholarship_programs_upserted += 1
        except Exception as e:
            logger.error(
                "Failed to upsert scholarship program (%s): %s",
                record.get("name"), str(e)
            )
            scholarship_programs_failed += 1
    # 5. Check which chunks already exist in the database (Idempotency check)
    chunk_ids = [chunk.metadata["id"] for chunk in chunks]
    existing_ids = check_existing_chunks(chunk_ids)
    logger.info("Found %d existing chunk IDs in RAG database", len(existing_ids))
    # Filter out chunks that are already ingested
    new_chunks = [c for c in chunks if c.metadata["id"] not in existing_ids]
    logger.info("Identified %d new chunks that require embedding and upsert", len(new_chunks))
    if not new_chunks:
        logger.info("All chunks already exist in the database. Ingestion completed with 0 updates.")
        summary = {
            "status": "degraded" if adapter_failures else "success",
            "dry_run": False,
            "processed_documents": len(documents),
            "total_chunks": len(chunks),
            "new_chunks_upserted": 0,
            "skipped_chunks": len(chunks),
            "visa_requirements_upserted": visa_requirements_upserted,
            "visa_requirements_failed": visa_requirements_failed,
            "program_requirements_upserted": program_requirements_upserted,
            "program_requirements_failed": program_requirements_failed,
            "scholarship_programs_upserted": scholarship_programs_upserted,
            "scholarship_programs_failed": scholarship_programs_failed,
            "docs_skipped_at_source": docs_skipped_at_source,
            "source_telemetry": source_telemetry,
            "adapter_failures": adapter_failures,
        }
        summary["report_key"] = write_completion_report(summary)
        return summary
    # 6. Generate embeddings for the new chunks
    new_texts = [c.page_content for c in new_chunks]
    embeddings = generate_embeddings(new_texts)
    logger.info("Generated %d embeddings using OpenAI", len(embeddings))
    # 7. Map chunks to upsert schema payloads
    upsert_payload = []
    for chunk, embedding in zip(new_chunks, embeddings):
        upsert_payload.append({
            "id": chunk.metadata["id"],
            "content": chunk.page_content,
            "embedding": embedding,
            "source_url": chunk.metadata.get("source_url"),
            "category": chunk.metadata.get("category")
        })
    # 8. Upsert to RAG service
    upsert_chunks(upsert_payload)
    logger.info("Bulk upsert of %d chunks completed successfully", len(new_chunks))
    summary = {
        "status": "degraded" if adapter_failures else "success",
        "dry_run": False,
        "processed_documents": len(documents),
        "total_chunks": len(chunks),
        "new_chunks_upserted": len(new_chunks),
        "skipped_chunks": len(chunks) - len(new_chunks),
        "visa_requirements_upserted": visa_requirements_upserted,
        "visa_requirements_failed": visa_requirements_failed,
        "program_requirements_upserted": program_requirements_upserted,
        "program_requirements_failed": program_requirements_failed,
        "scholarship_programs_upserted": scholarship_programs_upserted,
        "scholarship_programs_failed": scholarship_programs_failed,
        "docs_skipped_at_source": docs_skipped_at_source,
        "source_telemetry": source_telemetry,
        "adapter_failures": adapter_failures,
    }
    summary["report_key"] = write_completion_report(summary)
    return summary


if __name__ == "__main__":
    # Canonical runner (GOA-111): same entry point for CLI, Docker CMD, and Lambda.
    # Exits 0 on success, 1 on failure — `docker compose run --rm ingestion` reports it.
    # A source blocked outright yields status "degraded" and so exits 1: it produced
    # zero rows, and a green run over zero rows is what BUG-010a was made of.
    import json
    import sys

    try:
        summary = handle_ingestion({})
        print(json.dumps(summary, indent=2, default=str))
        failed = (
            summary.get("visa_requirements_failed", 0)
            + summary.get("program_requirements_failed", 0)
            + summary.get("scholarship_programs_failed", 0)
        )
        sys.exit(0 if summary.get("status") == "success" and failed == 0 else 1)
    except Exception as exc:  # noqa: BLE001 — the runner must never die silently
        logger.exception("Ingestion run failed: %s", exc)
        sys.exit(1)