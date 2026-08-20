import asyncio
import hashlib
import json
import time
import uuid
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import structlog
from app.schemas.query import QueryRequest, QueryResponse, DocumentSource
from app.services import rag_service
from app.core.logging import correlation_id_var
from app.core.metrics import QUERY_LATENCY, RETRIEVAL_SIMILARITY
from app.core.trace_context import parse_traceparent
from app.core.config import settings
from app.core.redis import redis_client

router = APIRouter()
logger = structlog.get_logger("rag_service.api.query")


def _flag_overrides(**values):
    mapping = {
        "rerank_enabled": values.get("rerank"),
        "threshold_enabled": values.get("threshold"),
        "retrieval_width": values.get("width"),
        "ivfflat_probes": values.get("probes"),
        "hybrid_enabled": values.get("hybrid"),
        "retrieval_only": values.get("retrieval_only"),
    }
    return {key: value for key, value in mapping.items() if value is not None}


def _response_sources(sources):
    response_sources = []
    for source in sources:
        fields = {
            "id": source["id"],
            "title": source.get("title"),
            "content": source["content"],
            "source_url": source["source_url"],
            "similarity": source["similarity"],
        }
        if "retrieval_arms" in source:
            fields["retrieval_arms"] = source["retrieval_arms"]
        response_sources.append(DocumentSource(**fields))
    return response_sources


def _cache_key(request: QueryRequest, flags: dict) -> str:
    material = json.dumps(
        {
            "question": " ".join(request.question.lower().split()),
            "user_id": request.userId,
            "top_k": request.topK or 5,
            "category": request.category,
            "flags": flags,
            "model": settings.llm_model,
            "max_tokens": settings.rag_answer_max_tokens,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"rag:query:v1:{hashlib.sha256(material.encode()).hexdigest()}"


async def _cache_get(key: str) -> QueryResponse | None:
    if not settings.rag_cache_enabled or redis_client.redis is None:
        return None
    try:
        cached = await redis_client.redis.get(key)
        return QueryResponse.model_validate_json(cached) if cached else None
    except Exception as exc:
        logger.warning("rag_cache_read_failed", error=str(exc))
        return None


async def _cache_set(key: str, response: QueryResponse) -> None:
    if not settings.rag_cache_enabled or redis_client.redis is None:
        return
    try:
        await redis_client.redis.set(
            key,
            response.model_dump_json(by_alias=True),
            ex=settings.rag_cache_ttl_seconds,
        )
    except Exception as exc:
        logger.warning("rag_cache_write_failed", error=str(exc))


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


@router.post(
    "/query",
    response_model=QueryResponse,
    response_model_exclude_unset=True,
)
async def handle_query(
    request: QueryRequest,
    x_correlation_id: str = Header(None, alias="X-Correlation-Id"),
    traceparent: str | None = Header(None, alias="traceparent"),
    x_rag_rerank: bool | None = Header(None, alias="X-RAG-Rerank-Enabled"),
    x_rag_threshold: bool | None = Header(None, alias="X-RAG-Threshold-Enabled"),
    x_rag_width: int | None = Header(None, alias="X-RAG-Retrieval-Width"),
    x_rag_probes: int | None = Header(None, alias="X-RAG-IVFFlat-Probes"),
    x_rag_hybrid: bool | None = Header(None, alias="X-RAG-Hybrid-Enabled"),
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

    flag_overrides = _flag_overrides(
        rerank=x_rag_rerank,
        threshold=x_rag_threshold,
        width=x_rag_width,
        probes=x_rag_probes,
        hybrid=x_rag_hybrid,
        retrieval_only=x_rag_retrieval_only,
    )
    cache_key = _cache_key(request, flag_overrides)
    cached = await _cache_get(cache_key)
    if cached is not None:
        QUERY_LATENCY.labels(cache_hit="true").observe(
            (time.time() - start_time) * 1000
        )
        if trace is not None:
            try:
                trace.update(
                    output={"answer": cached.answer},
                    metadata={"cache_hit": True},
                )
                trace.end()
            except Exception as exc:
                logger.warning("langfuse_trace_end_failed", error=str(exc))
        return cached

    try:
        answer, sources, metrics = await rag_service.query_rag(
            question=request.question,
            user_id=request.userId,
            top_k=request.topK or 5,
            category=request.category,
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
    if top_similarity is not None:
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

    response_sources = _response_sources(sources)

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

    result = QueryResponse(
        answer=answer,
        reason=reason,
        suggestion=suggestion,
        sources=response_sources
    )
    await _cache_set(cache_key, result)
    return result


@router.post("/query/stream")
async def handle_query_stream(
    request: QueryRequest,
    x_correlation_id: str = Header(None, alias="X-Correlation-Id"),
    traceparent: str | None = Header(None, alias="traceparent"),
    x_rag_rerank: bool | None = Header(None, alias="X-RAG-Rerank-Enabled"),
    x_rag_threshold: bool | None = Header(None, alias="X-RAG-Threshold-Enabled"),
    x_rag_width: int | None = Header(None, alias="X-RAG-Retrieval-Width"),
    x_rag_probes: int | None = Header(None, alias="X-RAG-IVFFlat-Probes"),
    x_rag_hybrid: bool | None = Header(None, alias="X-RAG-Hybrid-Enabled"),
):
    correlation_id = x_correlation_id or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)
    flags = _flag_overrides(
        rerank=x_rag_rerank,
        threshold=x_rag_threshold,
        width=x_rag_width,
        probes=x_rag_probes,
        hybrid=x_rag_hybrid,
    )
    cache_key = _cache_key(request, flags)

    async def event_generator():
        started = time.time()
        cached = await _cache_get(cache_key)
        if cached is not None:
            yield _sse("status", {
                "type": "status",
                "stage": "generating",
                "message": "Using a recent trusted answer…",
            })
            answer = cached.answer or cached.suggestion or ""
            if answer:
                yield _sse("token", {"type": "token", "content": answer})
            if cached.sources:
                yield _sse("sources", {
                    "type": "sources",
                    "sources": [source.model_dump(by_alias=True) for source in cached.sources],
                })
            QUERY_LATENCY.labels(cache_hit="true").observe(
                (time.time() - started) * 1000
            )
            yield _sse("done", {"type": "done"})
            return

        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        emitted_token = False
        trace = None
        if rag_service.langfuse_client is not None:
            try:
                trace = rag_service.langfuse_client.start_observation(
                    trace_context=parse_traceparent(traceparent),
                    name="rag-query-stream",
                    as_type="span",
                    input={"question": request.question},
                    metadata={
                        "user_id": request.userId,
                        "correlation_id": correlation_id,
                    },
                )
            except Exception as exc:
                logger.warning("langfuse_trace_start_failed", error=str(exc))

        async def on_token(content: str) -> None:
            nonlocal emitted_token
            emitted_token = True
            await queue.put(("token", {"type": "token", "content": content}))

        async def on_status(stage: str, message: str) -> None:
            await queue.put(("status", {
                "type": "status",
                "stage": stage,
                "message": message,
            }))

        async def run_query() -> None:
            try:
                answer, sources, metrics = await rag_service.query_rag(
                    question=request.question,
                    user_id=request.userId,
                    top_k=request.topK or 5,
                    category=request.category,
                    trace=trace,
                    flag_overrides=flags,
                    token_callback=on_token,
                    status_callback=on_status,
                )
                response = QueryResponse(
                    answer=answer,
                    reason=metrics.get("refusal_reason"),
                    suggestion=metrics.get("refusal_suggestion"),
                    sources=_response_sources(sources),
                )
                if not emitted_token:
                    fallback = response.answer or response.suggestion or ""
                    if fallback:
                        await on_token(fallback)
                if response.sources:
                    await queue.put(("sources", {
                        "type": "sources",
                        "sources": [
                            source.model_dump(by_alias=True)
                            for source in response.sources
                        ],
                    }))
                await _cache_set(cache_key, response)
                duration_ms = (time.time() - started) * 1000
                QUERY_LATENCY.labels(cache_hit="false").observe(duration_ms)
                top_similarity = metrics.get("top_similarity")
                if top_similarity is not None:
                    RETRIEVAL_SIMILARITY.observe(top_similarity)
                structlog.get_logger("rag_service.query_completion").info(
                    "query_completed",
                    correlation_id=correlation_id,
                    question_hash=metrics.get("question_hash"),
                    top_similarity=top_similarity,
                    chunks_retrieved=metrics.get("chunks_retrieved", 0),
                    cache_hit="false",
                    answer_tokens=metrics.get("answer_tokens", 0),
                    latency_ms=duration_ms,
                    refused=metrics.get("refused", False),
                    streamed=True,
                )
                if trace is not None:
                    try:
                        trace.update(
                            output={"answer": response.answer},
                            metadata={
                                "question_hash": metrics.get("question_hash"),
                                "top_similarity_score": top_similarity,
                                "streamed": True,
                            },
                        )
                        trace.end()
                    except Exception as exc:
                        logger.warning("langfuse_trace_end_failed", error=str(exc))
                await queue.put(("done", {"type": "done"}))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if trace is not None:
                    try:
                        trace.update(level="ERROR", status_message=str(exc))
                        trace.end()
                    except Exception:
                        pass
                logger.error(
                    "stream_query_failed",
                    correlation_id=correlation_id,
                    error=str(exc),
                )
                await queue.put(("error", {
                    "type": "error",
                    "error": "RAG query failed",
                }))

        task = asyncio.create_task(run_query())
        try:
            while True:
                event, payload = await queue.get()
                yield _sse(event, payload)
                if event in {"done", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
