import argparse
import asyncio
import datetime
import json
import logging
import os
import time
import uuid
from typing import Any

from app.adapters.chevening import CheveningAdapter
from app.adapters.daad import DAADAdapter
from app.adapters.ielts_org import IELTSOrgAdapter
from app.adapters.masters_portal import MastersPortalAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter
from app.adapters.study_in_poland import StudyInPolandAdapter
from app.adapters.visa_adapter import VisaSourceAdapter
from app.core.batch import BatchBudget, deadline_from_context
from app.core.crawl_state import CrawlStateManager
from chunker import chunk_documents
from client import (
    check_existing_chunks,
    delete_documents_by_source_url,
    upsert_chunks,
    upsert_program_requirement,
    upsert_scholarship_program,
    upsert_visa_requirement,
)
from config import settings
from embedder import generate_embeddings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingestion_worker.handler")


class IngestionRunFailed(RuntimeError):
    def __init__(self, summary: dict):
        super().__init__("Ingestion run exceeded its failure threshold")
        self.summary = summary


class CompletionReportError(RuntimeError):
    pass


def _adapter_instances(
    state: CrawlStateManager, budget: BatchBudget, dry_run: bool
) -> list[Any]:
    return [
        IELTSOrgAdapter(),
        DAADAdapter(),
        CheveningAdapter(),
        StudyInPolandAdapter(),
        StipendiumHungaricumAdapter(),
        MastersPortalAdapter(crawl_state_manager=state, budget=budget),
        VisaSourceAdapter(
            crawl_state_manager=state,
            budget=budget,
            dry_run=dry_run,
        ),
    ]


async def fetch_all_adapters(
    only: list[str] | None = None,
    tier: int = 2,
    *,
    state: CrawlStateManager | None = None,
    budget: BatchBudget | None = None,
    dry_run: bool = False,
):
    state = state or CrawlStateManager(read_only=dry_run)
    budget = budget or BatchBudget(
        max_items=int(os.getenv("INGESTION_MAX_ITEMS", "500")),
        deadline=time.monotonic()
        + float(os.getenv("INGESTION_WALL_CLOCK_BUDGET_SECONDS", "3600")),
    )
    adapters = _adapter_instances(state, budget, dry_run)
    if only:
        known = {adapter.source_name for adapter in adapters}
        unknown = sorted(set(only) - known)
        if unknown:
            raise ValueError(
                f"Unknown adapter(s) in INGESTION_ADAPTERS: {', '.join(unknown)}. "
                f"Known sources: {', '.join(sorted(known))}"
            )
        adapters = [adapter for adapter in adapters if adapter.source_name in only]

    if tier == 1:
        adapters = [adapter for adapter in adapters if hasattr(adapter, "scrape_cards")]

    from langchain_core.documents import Document

    all_docs = []
    all_visa_records = []
    all_program_records = []
    all_scholarship_records = []
    adapter_failures: dict[str, str] = {}
    source_telemetry: dict[str, dict] = {}

    # Scheduled events deliberately select one adapter. Sequential execution keeps
    # the item/deadline budget meaningful for manually requested multi-source runs.
    for adapter in adapters:
        if budget.exhausted:
            source_telemetry[adapter.source_name] = {"remaining": 1}
            continue
        logger.info("Scraping source: %s (tier %d)", adapter.source_name, tier)
        try:
            result = (
                await adapter.scrape_cards()
                if tier == 1 and hasattr(adapter, "scrape_cards")
                else await adapter.scrape()
            )
        except Exception as error:
            logger.exception("Adapter %s failed", adapter.source_name)
            adapter_failures[adapter.source_name] = (
                f"{type(error).__name__}: {error}"
            )
            source_telemetry[adapter.source_name] = {
                "failed": 1,
                "error": str(error),
            }
            continue

        source_telemetry[adapter.source_name] = (
            getattr(adapter, "last_run_telemetry", {}) or {}
        )
        for item in result:
            for record in item.pop("program_requirements", []):
                all_program_records.append(
                    {**record, "_ingestion_source": adapter.source_name}
                )
            for record in item.pop("scholarship_programs", []):
                all_scholarship_records.append(
                    {**record, "_ingestion_source": adapter.source_name}
                )
            for record in item.pop("visa_requirements", []):
                all_visa_records.append(
                    {**record, "_ingestion_source": adapter.source_name}
                )
            all_docs.append(
                Document(
                    page_content=item["content"],
                    metadata={
                        "source_url": item.get("source_url") or item.get("url"),
                        "category": item.get("category"),
                        "source_name": adapter.source_name,
                    },
                )
            )

    return (
        all_docs,
        all_visa_records,
        all_program_records,
        all_scholarship_records,
        source_telemetry,
        adapter_failures,
    )


def _report_bucket() -> str:
    explicit = os.getenv("INGESTION_REPORTS_BUCKET")
    if explicit:
        return explicit
    environment = os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "dev"
    return f"goa-ingestion-reports-{environment}"


def write_completion_report(summary: dict) -> str | None:
    if summary.get("dry_run"):
        return None
    try:
        import boto3

        started_at = summary.get("started_at") or datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        run_id = summary.get("run_id") or uuid.uuid4()
        timestamp_key = started_at.replace("+00:00", "Z").replace(":", "")
        key = (
            f"reports/{timestamp_key}"
            f"-{run_id}.json"
        )
        client = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
        client.put_object(
            Bucket=_report_bucket(),
            Key=key,
            Body=json.dumps(summary, indent=2, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Completion report written to s3://%s/%s", _report_bucket(), key)
        return key
    except Exception as error:
        logger.exception("Could not write completion report")
        raise CompletionReportError("Completion report could not be persisted") from error


def _sum_telemetry(source_telemetry: dict, key: str) -> int:
    total = 0
    for value in source_telemetry.values():
        if not isinstance(value, dict):
            continue
        if key in value and isinstance(value[key], (int, float)):
            total += int(value[key])
        else:
            total += sum(
                int(child.get(key, 0))
                for child in value.values()
                if isinstance(child, dict)
            )
    return total


def _source_reports(
    source_telemetry: dict,
    adapter_failures: dict,
    *,
    actions: dict[str, dict[str, int]] | None = None,
    state: CrawlStateManager | None = None,
) -> list[dict]:
    reports = []
    for name, telemetry in source_telemetry.items():
        nested = (
            [value for value in telemetry.values() if isinstance(value, dict)]
            if isinstance(telemetry, dict)
            else []
        )
        values = nested or ([telemetry] if isinstance(telemetry, dict) else [])
        actual = actions.get(name, {}) if actions is not None else {}
        last_success_at = (
            state.get_last_success_at(name)
            if state is not None and hasattr(state, "get_last_success_at")
            else None
        )
        reports.append(
            {
                "name": name,
                "added": int(
                    actual.get(
                        "added",
                        sum(int(value.get("extracted", 0)) for value in values),
                    )
                ),
                "updated": int(actual.get("updated", 0)),
                "skipped": sum(
                    int(value.get("skipped", 0)) for value in values
                )
                + int(actual.get("skipped", 0)),
                "failed": sum(int(value.get("failed", 0)) for value in values)
                + int(actual.get("failed", 0)),
                "remaining": sum(int(value.get("remaining", 0)) for value in values),
                "last_success_at": (
                    last_success_at.isoformat()
                    if hasattr(last_success_at, "isoformat")
                    else last_success_at
                ),
                "error": adapter_failures.get(name),
            }
        )
    return reports


def _emit_emf(summary: dict):
    counts = summary["counts"]
    logger.info(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "GOA/Ingestion",
                            "Dimensions": [["Environment"]],
                            "Metrics": [
                                {"Name": "FailureRate", "Unit": "Percent"},
                                {"Name": "Remaining", "Unit": "Count"},
                                {"Name": "FreshnessHeartbeat", "Unit": "Count"},
                            ],
                        }
                    ],
                },
                "Environment": os.getenv("ENVIRONMENT", "dev"),
                "FailureRate": summary["failure_ratio"] * 100,
                "Remaining": counts["remaining"],
                "FreshnessHeartbeat": 1
                if summary["status"] == "success"
                else 0,
                "run_id": summary["run_id"],
            }
        )
    )


def _action(result: Any) -> str:
    if isinstance(result, dict):
        action = result.get("action")
        if action in {"inserted", "updated", "unchanged"}:
            return action
    # Backwards-compatible test doubles that still return True represent a write.
    return "updated"


def _normalize_adapter_result(result):
    values = list(result)
    if len(values) == 2:
        values.extend([[], [], {}, {}])
    elif len(values) == 5:
        values.append({})
    if len(values) != 6:
        raise ValueError(f"Adapter result must contain 2, 5, or 6 values; got {len(values)}")
    return values


def handle_ingestion(
    event: dict,
    context=None,
    *,
    state_manager: CrawlStateManager | None = None,
    clock=time.monotonic,
) -> dict:
    event = event or {}
    run_id = str(event.get("run_id") or uuid.uuid4())
    started_wall = datetime.datetime.now(datetime.timezone.utc)
    started_clock = clock()
    dry_run = bool(event.get("dry_run", settings.dry_run))
    tier = int(event.get("tier") or os.getenv("INGESTION_TIER") or 2)
    only = event.get("adapters") or (
        [
            source.strip()
            for source in os.environ["INGESTION_ADAPTERS"].split(",")
            if source.strip()
        ]
        if os.getenv("INGESTION_ADAPTERS")
        else None
    )
    max_items = int(
        event.get("max_items") or os.getenv("INGESTION_MAX_ITEMS") or 500
    )
    wall_clock_budget_s = float(
        event.get("max_seconds")
        or os.getenv("INGESTION_WALL_CLOCK_BUDGET_SECONDS")
        or 3600
    )
    safety_margin_s = float(os.getenv("INGESTION_SAFETY_MARGIN_SECONDS", "120"))
    budget = BatchBudget(
        max_items=max_items,
        deadline=deadline_from_context(
            context,
            wall_clock_budget_s=wall_clock_budget_s,
            safety_margin_s=safety_margin_s,
            clock=clock,
        ),
        clock=clock,
    )
    state = state_manager or CrawlStateManager(read_only=dry_run)
    state.start_run(run_id)

    logger.info("Ingestion pipeline started with event: %s", event)
    adapter_result = asyncio.run(
        fetch_all_adapters(
            only=only,
            tier=tier,
            state=state,
            budget=budget,
            dry_run=dry_run,
        )
    )
    (
        documents,
        visa_records,
        program_records,
        scholarship_records,
        source_telemetry,
        adapter_failures,
    ) = _normalize_adapter_result(adapter_result)

    chunks = chunk_documents(documents)
    skipped_at_source = _sum_telemetry(source_telemetry, "skipped")
    failed_at_source = _sum_telemetry(source_telemetry, "failed")
    remaining = _sum_telemetry(source_telemetry, "remaining")
    llm_calls = _sum_telemetry(source_telemetry, "calls")
    llm_input_tokens = _sum_telemetry(source_telemetry, "input_tokens")
    llm_output_tokens = _sum_telemetry(source_telemetry, "output_tokens")

    if dry_run:
        for chunk in chunks:
            logger.info(
                "Would upsert chunk ID %s from source %s",
                chunk.metadata["id"],
                chunk.metadata.get("source_url"),
            )
        for record in visa_records:
            logger.info(
                "Would upsert visa requirement: %s / %s / %s",
                record.get("country"),
                record.get("visa_type"),
                record.get("issuing_body"),
            )
        finished_at = datetime.datetime.now(datetime.timezone.utc)
        summary = {
            "run_id": run_id,
            "started_at": started_wall.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_s": round(clock() - started_clock, 3),
            "tier": tier,
            "dry_run": True,
            "completed": remaining == 0 and failed_at_source == 0,
            "status": (
                "degraded"
                if adapter_failures or failed_at_source
                else "success"
            ),
            "counts": {
                "added": 0,
                "updated": 0,
                "skipped": skipped_at_source + len(chunks),
                "failed": failed_at_source,
                "remaining": remaining,
            },
            "llm": {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
            "sources": _source_reports(
                source_telemetry,
                adapter_failures,
                state=state,
            ),
            "adapter_failures": adapter_failures,
            "report_key": None,
            "processed_documents": len(documents),
            "total_chunks": len(chunks),
            "new_chunks_upserted": 0,
            "skipped_chunks": len(chunks),
            "docs_skipped_at_source": skipped_at_source,
            "source_telemetry": source_telemetry,
            "visa_requirements_upserted": 0,
            "visa_requirements_failed": 0,
            "program_requirements_upserted": 0,
            "program_requirements_failed": 0,
            "scholarship_programs_upserted": 0,
            "scholarship_programs_failed": 0,
        }
        return summary

    added = 0
    updated = 0
    skipped = skipped_at_source
    failed = failed_at_source
    visa_upserted = 0
    visa_failed = 0
    program_upserted = 0
    program_failed = 0
    scholarship_upserted = 0
    scholarship_failed = 0
    successful_program_urls: list[tuple[str, str]] = []
    successful_visa_sources: list[tuple[str, str]] = []
    source_actions: dict[str, dict[str, int]] = {}

    def record_action(source_name: str | None, action: str):
        if not source_name:
            return
        counters = source_actions.setdefault(
            source_name,
            {"added": 0, "updated": 0, "skipped": 0, "failed": 0},
        )
        key = {
            "inserted": "added",
            "updated": "updated",
            "unchanged": "skipped",
            "failed": "failed",
        }[action]
        counters[key] += 1

    document_result = {"added": 0, "updated": 0}
    existing_ids: set = set()
    new_chunks = []
    document_pipeline_succeeded = True
    source_urls = sorted(
        {
            chunk.metadata.get("source_url")
            for chunk in chunks
            if chunk.metadata.get("source_url")
        }
    )
    try:
        if chunks:
            if tier == 2:
                # Tier 2 replaces every old chunk for the source. Generate the
                # expensive embeddings first so an embedding outage cannot erase
                # the last good corpus before the replacement is ready.
                new_chunks = chunks
            else:
                chunk_ids = [chunk.metadata["id"] for chunk in chunks]
                existing_ids = set(check_existing_chunks(chunk_ids))
                new_chunks = [
                    chunk
                    for chunk in chunks
                    if chunk.metadata["id"] not in existing_ids
                ]
                skipped += len(chunks) - len(new_chunks)
                for chunk in chunks:
                    if chunk.metadata["id"] in existing_ids:
                        record_action(
                            chunk.metadata.get("source_name"), "unchanged"
                        )

            if new_chunks:
                embeddings = generate_embeddings(
                    [chunk.page_content for chunk in new_chunks]
                )
                if tier == 2:
                    for source_url in source_urls:
                        delete_documents_by_source_url(source_url)
                payload = [
                    {
                        "id": chunk.metadata["id"],
                        "content": chunk.page_content,
                        "embedding": embedding,
                        "source_url": chunk.metadata.get("source_url"),
                        "category": chunk.metadata.get("category"),
                    }
                    for chunk, embedding in zip(new_chunks, embeddings)
                ]
                raw_document_result = upsert_chunks(payload)
                document_result = (
                    raw_document_result
                    if isinstance(raw_document_result, dict)
                    else {"added": len(new_chunks), "updated": 0}
                )
                added += int(document_result.get("added", len(new_chunks)))
                updated += int(document_result.get("updated", 0))
                for chunk in new_chunks:
                    record_action(
                        chunk.metadata.get("source_name"), "inserted"
                    )
    except Exception:
        document_pipeline_succeeded = False
        document_failures = max(1, len(chunks))
        failed += document_failures
        for chunk in chunks:
            record_action(chunk.metadata.get("source_name"), "failed")
        for record in visa_records:
            source_key = record.get("_ingestion_source_key")
            source_url = record.get("source_url")
            if source_key and source_url:
                state.mark_source_attempt(
                    record.get("_ingestion_source") or "visa_adapter",
                    source_key,
                    source_url,
                    succeeded=False,
                    error_message="document_pipeline_failed",
                )
        logger.exception("Document replacement/upsert pipeline failed")

    # Persist structured rows only after the document leg succeeds. In
    # particular, the visa content_hash is the next run's LLM skip gate: writing
    # it before its document would make a failed document upsert look unchanged
    # forever and prevent the missing chunk from being rebuilt.
    if document_pipeline_succeeded:
        for record in visa_records:
            payload = dict(record)
            source_name = payload.pop("_ingestion_source", None)
            source_key = payload.pop("_ingestion_source_key", None)
            source_url = payload.get("source_url")
            try:
                action = _action(upsert_visa_requirement(payload))
                record_action(source_name, action)
                if action == "inserted":
                    added += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
                if source_key and source_url:
                    successful_visa_sources.append((source_key, source_url))
                visa_upserted += 1
            except Exception as error:
                record_action(source_name, "failed")
                failed += 1
                visa_failed += 1
                if source_key and source_url:
                    state.mark_source_attempt(
                        source_name or "visa_adapter",
                        source_key,
                        source_url,
                        succeeded=False,
                        error_message=f"structured_upsert_failed: {error}",
                    )
                logger.exception("Failed to upsert visa requirement")

        for record in program_records:
            payload = dict(record)
            source_name = payload.pop("_ingestion_source", None)
            try:
                action = _action(upsert_program_requirement(payload))
                record_action(source_name, action)
                if action == "inserted":
                    added += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
                source_url = payload.get("source_url")
                if source_url and "mastersportal.com" in source_url:
                    successful_program_urls.append(
                        (source_url, payload.get("discipline") or "unknown")
                    )
                program_upserted += 1
            except Exception:
                record_action(source_name, "failed")
                failed += 1
                program_failed += 1
                logger.exception("Failed to upsert program requirement")

        for record in scholarship_records:
            payload = dict(record)
            source_name = payload.pop("_ingestion_source", None)
            try:
                action = _action(upsert_scholarship_program(payload))
                record_action(source_name, action)
                if action == "inserted":
                    added += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
                scholarship_upserted += 1
            except Exception:
                record_action(source_name, "failed")
                failed += 1
                scholarship_failed += 1
                logger.exception("Failed to upsert scholarship program")

    if document_pipeline_succeeded:
        for source_key, source_url in successful_visa_sources:
            state.mark_source_attempt(
                "visa_adapter",
                source_key,
                source_url,
                succeeded=True,
            )
        for source_url, discipline in successful_program_urls:
            state.mark_url_status(
                "masters_portal", discipline, source_url, "scraped"
            )
        if tier == 2:
            for source_url in source_urls:
                state.mark_page_status(source_url, "fetched")

    attempted = added + updated + skipped + failed
    failure_ratio = failed / attempted if attempted else 0.0
    status = "degraded" if failed or failure_ratio > 0.10 else "success"
    completed = remaining == 0 and failed == 0
    finished_at = datetime.datetime.now(datetime.timezone.utc)
    input_cost = float(os.getenv("EXTRACTION_INPUT_COST_PER_1M", "8"))
    output_cost = float(os.getenv("EXTRACTION_OUTPUT_COST_PER_1M", "40"))
    summary = {
        "run_id": run_id,
        "started_at": started_wall.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": round(clock() - started_clock, 3),
        "tier": tier,
        "dry_run": False,
        "completed": completed,
        "status": status,
        "counts": {
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "remaining": remaining,
        },
        "llm": {
            "calls": llm_calls,
            "input_tokens": llm_input_tokens,
            "output_tokens": llm_output_tokens,
            "estimated_cost_usd": round(
                llm_input_tokens * input_cost / 1_000_000
                + llm_output_tokens * output_cost / 1_000_000,
                6,
            ),
        },
        "sources": _source_reports(
            source_telemetry,
            adapter_failures,
            actions=source_actions,
            state=state,
        ),
        "adapter_failures": adapter_failures,
        "failure_ratio": failure_ratio,
        # Compatibility fields retained for existing operators and tests.
        "processed_documents": len(documents),
        "total_chunks": len(chunks),
        "new_chunks_upserted": int(document_result.get("added", 0))
        + int(document_result.get("updated", 0)),
        "skipped_chunks": len(chunks) - len(new_chunks),
        "docs_skipped_at_source": skipped_at_source,
        "source_telemetry": source_telemetry,
        "visa_requirements_upserted": visa_upserted,
        "visa_requirements_failed": visa_failed,
        "program_requirements_upserted": program_upserted,
        "program_requirements_failed": program_failed,
        "scholarship_programs_upserted": scholarship_upserted,
        "scholarship_programs_failed": scholarship_failed,
    }
    state.finish_run(
        run_id,
        completed=completed,
        remaining=remaining,
        error_message=None if status == "success" else "failure threshold exceeded",
    )
    summary["report_key"] = write_completion_report(summary)
    _emit_emf(summary)
    if status != "success":
        raise IngestionRunFailed(summary)
    return summary


def consume_queue(*, once: bool = False):
    import boto3

    queue_url = os.getenv("INGESTION_QUEUE_URL")
    if not queue_url:
        raise RuntimeError("INGESTION_QUEUE_URL is required for queue-consumer mode")
    sqs = boto3.client("sqs", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            # This must exceed the one-hour work window plus shutdown/report
            # headroom. A shorter per-receive override defeats the queue's own
            # 72-minute setting and lets a second worker pick up an in-flight job.
            VisibilityTimeout=int(os.getenv("INGESTION_VISIBILITY_TIMEOUT", "4320")),
        )
        for message in response.get("Messages", []):
            event = json.loads(message["Body"])
            try:
                handle_ingestion(event)
            except Exception:
                logger.exception("Queued ingestion run failed; message left for retry")
                continue
            sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        if once:
            return


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-json")
    parser.add_argument("--consume-queue", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.consume_queue:
        consume_queue(once=args.once)
        return 0
    event = json.loads(args.event_json) if args.event_json else {}
    try:
        summary = handle_ingestion(event)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as error:
        if isinstance(error, IngestionRunFailed):
            print(json.dumps(error.summary, indent=2, default=str))
        else:
            logger.exception("Ingestion run failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
