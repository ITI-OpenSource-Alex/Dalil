import time
import uuid
from fastapi import APIRouter, Header, HTTPException
import structlog
from app.schemas.query import QueryRequest, QueryResponse, DocumentSource
from app.services import rag_service
from app.core.logging import correlation_id_var
from app.core.metrics import QUERY_LATENCY, RETRIEVAL_SIMILARITY
from app.core.trace_context import parse_traceparent

router = APIRouter()
logger = structlog.get_logger("rag_service.api.query")


@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    x_correlation_id: str = Header(None, alias="X-Correlation-Id"),
    traceparent: str | None = Header(None, alias="traceparent"),
    x_rag_rerank: bool | None = Header(None, alias="X-RAG-Rerank-Enabled"),
    x_rag_threshold: bool | None = Header(None, alias="X-RAG-Threshold-Enabled"),
    x_rag_width: int | None = Header(None, alias="X-RAG-Retrieval-Width"),
    x_rag_probes: int | None = Header(None, alias="X-RAG-IVFFlat-Probes"),
    # Eval affordance: return retrieval results without generating an answer.
    # Retrieval quality (MRR, relevant@k, recall@k) is computed entirely from `sources`,
    # which exist before the LLM is called -- so a benchmark of retrieval should not be
    # able to fail because generation is unavailable. Without this, an expired LLM key
    # turns every query into a 500 and the harness records a quality collapse that is
    # really an outage. That is the exact defect this ticket found in run_rag_eval.
    # No effect on the normal path: the header is absent in production traffic.
    x_rag_retrieval_only: bool | None = Header(None, alias="X-RAG-Retrieval-Only"),
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

    flag_overrides = {}
    if x_rag_rerank is not None:
        flag_overrides["rerank_enabled"] = x_rag_rerank
    if x_rag_threshold is not None:
        flag_overrides["threshold_enabled"] = x_rag_threshold
    if x_rag_width is not None:
        flag_overrides["retrieval_width"] = x_rag_width
    if x_rag_probes is not None:
        flag_overrides["ivfflat_probes"] = x_rag_probes
    if x_rag_retrieval_only is not None:
        flag_overrides["retrieval_only"] = x_rag_retrieval_only

    try:
        answer, sources, metrics = await rag_service.query_rag(
            question=request.question,
            user_id=request.userId,
            top_k=request.topK or 5,
            trace=trace,
            flag_overrides=flag_overrides,
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
    QUERY_LATENCY.labels(cache_hit="false").observe(duration_ms)

    top_similarity = metrics["top_similarity"]
    RETRIEVAL_SIMILARITY.observe(top_similarity)

    # Emit structured completion JSON log
    completion_logger = structlog.get_logger("rag_service.query_completion")
    completion_logger.info(
        "query_completed",
        correlation_id=correlation_id,
        question_hash=metrics["question_hash"],
        top_similarity=top_similarity,
        chunks_retrieved=metrics["chunks_retrieved"],
        cache_hit="false",
        answer_tokens=metrics["answer_tokens"],
        latency_ms=duration_ms,
        refused=metrics.get("refused", False),
    )

    response_sources = [
        DocumentSource(
            id=s["id"],
            title=s.get("title"),
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

    reason = metrics.get("refusal_reason")
    suggestion = metrics.get("refusal_suggestion")

    return QueryResponse(
        answer=answer,
        reason=reason,
        suggestion=suggestion,
        sources=response_sources
    )
