import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import unquote_plus
from uuid import uuid4

import boto3

from app.config import MAX_CV_SIZE_BYTES, Settings, get_settings
from app.runtime_secrets import load_writing_runtime_secrets

load_writing_runtime_secrets()

from app.database import SessionLocal  # noqa: E402
from app.metrics import CV_EXTRACTION_DURATION_MS, CV_EXTRACTION_TOTAL  # noqa: E402
from app.models import CVReview  # noqa: E402
from app.observability import get_langfuse_client, trace_cv_extraction  # noqa: E402
from app.services.event_publisher import publish_cv_processed  # noqa: E402
from cv_processor.extraction import UnsupportedCVType, detect_file_type, extract_plain_text  # noqa: E402
from cv_processor.structured import StructuredCVExtractor  # noqa: E402


logger = logging.getLogger("writing.cv_processor")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COLD_START = True


class CVProcessorConfigurationError(RuntimeError):
    """Raised before processing when a required worker credential is unavailable."""


class CVProcessor:
    def __init__(
        self,
        *,
        s3_client: Any,
        sqs_client: Any,
        session_factory: Any,
        structured_extractor: StructuredCVExtractor,
        settings: Settings,
        langfuse_client: Any = None,
    ) -> None:
        self.s3 = s3_client
        self.sqs = sqs_client
        self.session_factory = session_factory
        self.structured_extractor = structured_extractor
        self.settings = settings
        self.langfuse = langfuse_client

    def process_record(self, record: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        bucket = record["s3"]["bucket"]["name"]
        s3_key = unquote_plus(record["s3"]["object"]["key"])
        user_id = _user_id_from_key(s3_key)
        correlation_id = record.get("responseElements", {}).get(
            "x-amz-request-id", str(uuid4())
        )
        file_type = PurePosixPath(s3_key).suffix.lower().lstrip(".") or "unknown"
        text_length = 0
        fields_extracted = 0
        outcome = "fail"

        try:
            head = self.s3.head_object(Bucket=bucket, Key=s3_key)
            content_length = int(head.get("ContentLength", 0))
            metadata_hash = str(head.get("Metadata", {}).get("sha256", "")).lower()
            if not SHA256_PATTERN.fullmatch(metadata_hash):
                metadata_hash = ""

            with self.session_factory() as db:
                review = self._ensure_review(db, user_id, s3_key)

                if metadata_hash and self._is_ready_duplicate(review, metadata_hash):
                    outcome = "skipped"
                    text_length = len(review.extracted_text or "")
                    fields_extracted = _fields_extracted(review.structured_data)
                    self._publish(review, correlation_id)
                    return self._result(review, outcome)

                if content_length > MAX_CV_SIZE_BYTES:
                    self._mark_failed(
                        db,
                        review,
                        f"CV exceeds the {MAX_CV_SIZE_BYTES}-byte size limit",
                        metadata_hash or None,
                        correlation_id,
                    )
                    return self._result(review, outcome)

                try:
                    file_type = detect_file_type(s3_key, head.get("ContentType"))
                except UnsupportedCVType as exc:
                    self._mark_failed(
                        db, review, str(exc), metadata_hash or None, correlation_id
                    )
                    return self._result(review, outcome)

                body = self.s3.get_object(Bucket=bucket, Key=s3_key)["Body"].read(
                    MAX_CV_SIZE_BYTES + 1
                )
                if len(body) > MAX_CV_SIZE_BYTES:
                    self._mark_failed(
                        db,
                        review,
                        f"CV exceeds the {MAX_CV_SIZE_BYTES}-byte size limit",
                        metadata_hash or None,
                        correlation_id,
                    )
                    return self._result(review, outcome)

                content_hash = hashlib.sha256(body).hexdigest()
                if self._is_ready_duplicate(review, content_hash):
                    outcome = "skipped"
                    text_length = len(review.extracted_text or "")
                    fields_extracted = _fields_extracted(review.structured_data)
                    self._publish(review, correlation_id)
                    return self._result(review, outcome)

                review.status = "processing"
                review.content_hash = content_hash
                review.error_message = None
                review.processed_at = None
                db.flush()

                try:
                    extracted_text = extract_plain_text(body, file_type)
                    text_length = len(extracted_text)
                    execution = self.structured_extractor.extract(extracted_text)
                    structured_data = execution.data.model_dump()
                    fields_extracted = execution.data.fields_extracted()
                except Exception as exc:
                    self._mark_failed(
                        db, review, str(exc), content_hash, correlation_id
                    )
                    return self._result(review, outcome)

                review.extracted_text = extracted_text
                review.structured_data = structured_data
                review.status = "ready"
                review.error_message = None
                review.processed_at = datetime.now(timezone.utc)
                db.commit()

                trace_cv_extraction(
                    self.langfuse,
                    user_id=user_id,
                    cv_id=review.id,
                    model=self.structured_extractor.model,
                    input_tokens=execution.input_tokens,
                    output_tokens=execution.output_tokens,
                    latency_ms=execution.latency_ms,
                    cost_usd=execution.cost_usd,
                    fields_extracted=fields_extracted,
                )
                self._publish(review, correlation_id)
                outcome = "success"
                return self._result(review, outcome)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            CV_EXTRACTION_DURATION_MS.observe(duration_ms)
            CV_EXTRACTION_TOTAL.labels(outcome=outcome).inc()
            logger.info(
                json.dumps(
                    {
                        "userId": user_id,
                        "cvId": locals().get("review").id
                        if locals().get("review") is not None
                        else None,
                        "file_type": file_type,
                        "text_length": text_length,
                        "fields_extracted": fields_extracted,
                        "duration_ms": round(duration_ms, 2),
                        "outcome": outcome,
                    },
                    separators=(",", ":"),
                )
            )

    def _ensure_review(self, db: Any, user_id: str, s3_key: str) -> CVReview:
        review = (
            db.query(CVReview)
            .filter(CVReview.s3_key == s3_key)
            .with_for_update()
            .one_or_none()
        )
        if review is not None:
            return review
        review = CVReview(
            user_id=user_id,
            s3_key=s3_key,
            original_filename=PurePosixPath(s3_key).name[:255],
            status="pending",
        )
        db.add(review)
        db.flush()
        return review

    @staticmethod
    def _is_ready_duplicate(review: CVReview, content_hash: str) -> bool:
        return review.status == "ready" and review.content_hash == content_hash

    def _mark_failed(
        self,
        db: Any,
        review: CVReview,
        message: str,
        content_hash: str | None,
        correlation_id: str,
    ) -> None:
        review.status = "failed"
        review.content_hash = content_hash
        review.extracted_text = None
        review.structured_data = None
        review.error_message = (message or "CV processing failed")[:2048]
        review.processed_at = datetime.now(timezone.utc)
        db.commit()
        self._publish(review, correlation_id)

    def _publish(self, review: CVReview, correlation_id: str) -> None:
        publish_cv_processed(
            sqs_client=self.sqs,
            queue_url=self.settings.cv_processed_queue_url,
            user_id=review.user_id,
            cv_id=review.id,
            s3_key=review.s3_key,
            processing_status=review.status,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _result(review: CVReview, outcome: str) -> dict[str, Any]:
        return {
            "cvId": review.id,
            "s3Key": review.s3_key,
            "status": review.status,
            "outcome": outcome,
        }


def _user_id_from_key(s3_key: str) -> str:
    parts = PurePosixPath(s3_key).parts
    if len(parts) < 3 or parts[0] != "cvs" or not parts[1]:
        raise ValueError("CV object key must match cvs/{userId}/{filename}")
    return parts[1][:128]


def _fields_extracted(structured_data: dict[str, Any] | None) -> int:
    return sum(
        value not in (None, "", []) for value in (structured_data or {}).values()
    )


def _memory_used_mb() -> float:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return round(float(usage.ru_maxrss) / 1024.0, 2)
    except Exception:
        return 0.0


def _iter_s3_records(event: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for record in event.get("Records", []):
        if "s3" in record:
            yield record
            continue
        if str(record.get("eventSource", "")).lower() == "aws:sqs":
            body = record.get("body", "{}")
            wrapped_event = json.loads(body) if isinstance(body, str) else body
            yield from _iter_s3_records(wrapped_event)


def _aws_client(service_name: str, settings: Settings) -> Any:
    return boto3.client(
        service_name,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        endpoint_url=settings.aws_endpoint_url,
    )


@lru_cache
def get_processor() -> CVProcessor:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise CVProcessorConfigurationError(
            "ANTHROPIC_API_KEY is not configured; retaining the event for retry"
        )

    from anthropic import Anthropic

    # Mirror app/agents.py. Without base_url this client talks to the real Anthropic
    # API instead of the AgentRouter gateway the rest of the stack uses, and the
    # gateway also requires the pinned User-Agent. get_settings() already resolves
    # ANTHROPIC_AUTH_TOKEN ahead of ANTHROPIC_API_KEY, so the routing bits were the
    # only thing missing here (BUG-018).
    anthropic_client = Anthropic(
        api_key=settings.anthropic_api_key,
        # NOT anthropic_timeout_seconds. That ceiling is tuned for the four
        # user-facing criterion agents; this is a background worker with nobody
        # watching, and extraction was measured timing out at 90s and succeeding
        # under 280s. See the comment on cv_extraction_timeout_seconds in
        # app/config.py, which is coupled to the queue's VisibilityTimeout.
        timeout=settings.cv_extraction_timeout_seconds,
        default_headers={"User-Agent": settings.anthropic_user_agent},
        **({"base_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    )
    return CVProcessor(
        s3_client=_aws_client("s3", settings),
        sqs_client=_aws_client("sqs", settings),
        session_factory=SessionLocal,
        structured_extractor=StructuredCVExtractor(
            anthropic_client, model=settings.cv_extraction_model
        ),
        settings=settings,
        langfuse_client=get_langfuse_client(),
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    global COLD_START
    started = time.perf_counter()
    records = list(_iter_s3_records(event))
    request_id = getattr(context, "aws_request_id", None)
    function_name = getattr(context, "function_name", "goa-cv-processor")
    outcome = "success"
    response: dict[str, Any]

    if not records:
        logger.warning("CV processor invocation contained no S3 records")
        response = {"processed": 0, "results": []}
        outcome = "empty"
    else:
        processor = get_processor()
        results = [processor.process_record(record) for record in records]
        response = {"processed": len(results), "results": results}
        if any(result.get("status") == "failed" for result in results):
            outcome = "partial_failure"

    logger.info(
        json.dumps(
            {
                "function_name": function_name,
                "request_id": request_id,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "memory_used_mb": _memory_used_mb(),
                "cold_start": COLD_START,
                "records_processed": len(records),
                "outcome": outcome,
            },
            separators=(",", ":"),
        )
    )
    COLD_START = False
    return response
