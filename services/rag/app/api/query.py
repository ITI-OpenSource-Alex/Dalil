import time
import uuid
from fastapi import APIRouter, Header, HTTPException
import structlog
from app.schemas.query import QueryRequest, QueryResponse, DocumentSource
from app.services.rag_service import query_rag
from app.core.logging import correlation_id_var
from app.core.metrics import QUERY_LATENCY, RETRIEVAL_SIMILARITY, LOW_CONFIDENCE_TOTAL
router = APIRouter()
logger = structlog.get_logger("rag_service.api.query")


@router.post('/query', response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    x_correlation_id: str = Header(None, alias="X-Correlation-Id")
):
    correlation_id = x_correlation_id or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)


    start_time = time.time()

    try:
        answer, sources, metrics = await query_rag(
            question=request.question,
            user_id=request.userId,
            top_k=request.topK or 5
        )
    except Exception as e:
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
        latency_ms=duration_ms
    )

    response_sources = [
        DocumentSource(
            id=s["id"],
            content=s["content"],
            source_url=s["source_url"],
            similarity=s["similarity"]
        ) for s in sources
    ]
    
    return QueryResponse(answer=answer, sources=response_sources)
