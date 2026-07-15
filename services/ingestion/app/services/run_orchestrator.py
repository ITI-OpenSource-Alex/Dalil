import asyncio
import uuid
from datetime import datetime
import structlog
from langchain_core.documents import Document
from app.adapters.ielts_org import IELTSOrgAdapter
from app.adapters.daad import DAADAdapter
from app.adapters.chevening import CheveningAdapter
from app.adapters.study_in_poland import StudyInPolandAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter
from app.adapters.masters_portal import MastersPortalAdapter
from app.adapters.german_embassy_cairo import GermanEmbassyCairoAdapter
from app.adapters.campus_france_egypt import CampusFranceEgyptAdapter
from app.adapters.uk_visa_egypt import UKVISAEgyptAdapter
from app.adapters.fintiba_sperrkonto import FintibaSperrkontoAdapter
from app.adapters.czech_embassy_cairo import CzechEmbassyCairoAdapter
from app.adapters.spain_visa_egypt import SpainVisaEgyptAdapter
from app.adapters.italy_embassy_cairo import ItalyEmbassyCairoAdapter
from app.services.s3_reporting import upload_report_to_s3
from app.core.metrics import DOCS_PROCESSED_TOTAL, RUN_DURATION_SECONDS
from client import upsert_visa_requirement


logger = structlog.get_logger(__name__)



async def run_ingestion():
    run_id = str(uuid.uuid4())
    start_time = datetime.utcnow()
    logger.info("ingestion_run_started", run_id=run_id)


    adapters = [
        IELTSOrgAdapter(),
        DAADAdapter(),
        CheveningAdapter(),
        StudyInPolandAdapter(),
        StipendiumHungaricumAdapter(),
        MastersPortalAdapter(),
        GermanEmbassyCairoAdapter(),
        CampusFranceEgyptAdapter(),
        UKVISAEgyptAdapter(),
        FintibaSperrkontoAdapter(),
        CzechEmbassyCairoAdapter(),
        SpainVisaEgyptAdapter(),
        ItalyEmbassyCairoAdapter(),
    ]

    #Run all 13 concurrently. return_exceptions=True is critical for isolation!
    results = await asyncio.gather(*[adapter.scrape() for adapter in adapters], return_exceptions=True)
    report = {
        "run_id": run_id,
        "started_at": start_time.isoformat(),
        "sources": [],
        "total_embedding_tokens": 0,
        "visa_requirements_upserted": 0,
        "visa_requirements_failed": 0
    }

    total_processed = 0
    total_skipped = 0
    total_failed = 0

    for adapter, result in zip(adapters, results):
        source_name = adapter.source_name
        
        # Did this adapter crash completely?
        if isinstance(result, Exception):
            logger.error("adapter_failed_completely", source=source_name, error=str(result))
            DOCS_PROCESSED_TOTAL.labels(source=source_name, outcome="fail").inc()
            report["sources"].append({
                "name": source_name,
                "docs_processed": 0,
                "docs_skipped": 0,
                "docs_failed": 1
            })
            total_failed += 1
            continue
        # Result is a list of dicts. We convert them to LangChain Documents for GOA-010 pipeline
        documents = []
        for doc_dict in result:
            # Structured visa requirements (GOA-086) are upserted independently of the
            # document chunk pipeline below -- pop them out first so they never leak into
            # chunk metadata, and so a failure on one side never blocks the other
            # (dual-write strategy, see implementation plan Task 16).
            visa_records = doc_dict.pop("visa_requirements", [])
            for visa_record in visa_records:
                try:
                    upsert_visa_requirement(visa_record)
                    report["visa_requirements_upserted"] += 1
                except Exception as e:
                    logger.error(
                        "visa_requirement_upsert_failed",
                        source=source_name,
                        issuing_body=visa_record.get("issuing_body"),
                        error=str(e)
                    )
                    report["visa_requirements_failed"] += 1

            documents.append(Document(
                page_content=doc_dict.pop("content"),
                metadata=doc_dict
            ))


        # Rag Ingestion
        doc_count = len(documents)
        DOCS_PROCESSED_TOTAL.labels(source=source_name, outcome="success").inc(doc_count)
        
        report["sources"].append({
            "name": source_name,
            "docs_processed": doc_count,
            "docs_skipped": 0, 
            "docs_failed": 0
        })
        total_processed += doc_count

    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    RUN_DURATION_SECONDS.set(duration)
    report["finished_at"] = end_time.isoformat()
    report["duration_s"] = duration
    #  Compute >10% failure ratio for alerting
    total_attempts = total_processed + total_failed
    if total_attempts > 0:
        failure_ratio = total_failed / total_attempts
        if failure_ratio > 0.1:
            logger.error("high_failure_ratio_alarm", ratio=failure_ratio, threshold=0.1)
    #  Flat Structured Log
    logger.info("ingestion_run_completed",
        docs_processed=total_processed,
        docs_skipped=total_skipped,
        docs_failed=total_failed,
        embedding_tokens_used=report["total_embedding_tokens"],
        duration_s=duration,
        visa_requirements_upserted=report["visa_requirements_upserted"],
        visa_requirements_failed=report["visa_requirements_failed"]
    )
    #  Rich S3 Report
    upload_report_to_s3(run_id, report)
if __name__ == "__main__":
    asyncio.run(run_ingestion())