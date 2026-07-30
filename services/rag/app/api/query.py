import time
import uuid
from fastapi import APIRouter, Header, HTTPException
import structlog
from app.schemas.query import QueryRequest, QueryResponse, DocumentSource
from app.services import rag_service
from app.core.logging import correlation_id_var
from app.core.metrics import QUERY_LATENCY, RETRIEVAL_SIMILARITY, LOW_CONFIDENCE_TOTAL
from app.core.trace_context import parse_traceparent

router = APIRouter()
logger = structlog.get_logger("rag_service.api.query")


@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    x_correlation_id: str = Header(None, alias="X-Correlation-Id"),
    traceparent: str | None = Header(None, alias="traceparent"),
):
    correlation_id = x_correlation_id or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)

    start_time = time.time()

    trace = None
    if rag_service.langfuse_client is not None:
        try:
            trace = rag_service.langfuse_client.start_observation(
                trace_context=parse_traceparent(traceparent),
                name="rag-query",
                as_type="span",
                input={"question": request.question},
                metadata={
                    "user_id": request.userId,
                    "correlation_id": correlation_id,
                },
            )
        except Exception as exc:
            logger.warning("langfuse_trace_start_failed", error=str(exc))

    try:
        answer, sources, metrics = await rag_service.query_rag(
            question=request.question,
            user_id=request.userId,
            top_k=request.topK or 5,
            trace=trace,
        )
    except Exception as e:
        if trace is not None:
            try:
                trace.update(level="ERROR", status_message=str(e))
                trace.end()
            except Exception:
                pass
        logger.error("Query generation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Query Generation Error")

    duration_ms = (time.time() - start_time) * 1000

    # Update Prometheus metrics
    # cache_hit is hardcoded to "false" as per the requirement
    QUERY_LATENCY.labels(cache_hit="false").observe(duration_ms)

    top_similarity = metrics["top_similarity"]
    RETRIEVAL_SIMILARITY.observe(top_similarity)

    if top_similarity < 0.6:
        LOW_CONFIDENCE_TOTAL.inc()

    # Emit structured completion JSON log
    completion_logger = structlog.get_logger("rag_service.query_completion")
    completion_logger.info(
        "query_completed",
        correlation_id=correlation_id,
        question_hash=metrics["question_hash"],
        top_similarity=top_similarity,
        chunks_retrieved=metrics["chunks_retrieved"],
        cache_hit="false",  # TODO: Update in GOA-015 once caching is implemented
        answer_tokens=metrics["answer_tokens"],
        latency_ms=duration_ms,
    )

    response_sources = [
        DocumentSource(
            id=s["id"],
            content=s["content"],
            source_url=s["source_url"],
            similarity=s["similarity"],
        )
        for s in sources
    ]

    if trace is not None:
        try:
            trace.update(
                output={"answer": answer},
                metadata={
                    "question_hash": metrics["question_hash"],
                    "top_similarity_score": top_similarity,
                },
            )
            trace.end()
        except Exception as exc:
            logger.warning("langfuse_trace_end_failed", error=str(exc))

    return QueryResponse(answer=answer, sources=response_sources)
