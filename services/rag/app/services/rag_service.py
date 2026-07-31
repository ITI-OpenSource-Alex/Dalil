import hashlib
import time
import logging
from typing import List, Tuple, Dict, Any
from openai import AsyncOpenAI

from langchain_anthropic import ChatAnthropic
from langfuse import Langfuse

from app.core.config import settings
from app.core.database import db

logger = logging.getLogger("rag_service.rag_service")

langfuse_client = None

if settings.langfuse_public_key and settings.langfuse_secret_key:
    langfuse_client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )

anthropic_key = settings.anthropic_api_key or "mock-key"

embedding_client = AsyncOpenAI(
    api_key=settings.embedding_api_key,
    base_url=settings.embedding_base_url
)

llm = ChatAnthropic(
    model=settings.llm_model,
    anthropic_api_key=settings.anthropic_auth_token or settings.anthropic_api_key,
    **({"anthropic_api_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    model_kwargs={"extra_headers": {"User-Agent": settings.anthropic_user_agent}},
    # langchain_anthropic 0.1.13 has no `timeout` or `max_retries` field on
    # ChatAnthropic; unrecognized kwargs are forwarded to AsyncMessages.create(),
    # which rejects max_retries — that made every /query return 500. The supported
    # field is default_request_timeout, and the retry now lives at the call site.
    default_request_timeout=25.0,
)


class _LLMResponse:
    """Minimal stand-in for a LangChain message: `.content` plus `.response_metadata`."""

    def __init__(self, content: str, usage):
        self.content = content
        self.response_metadata = {"usage": usage} if usage is not None else {}


async def _invoke_via_sdk(prompt) -> _LLMResponse:
    """Call the gateway through the raw Anthropic SDK, tolerating thinking blocks.

    langchain_anthropic 0.1.13 predates extended thinking and reads `content[0].text`
    unconditionally, so any response whose first block is a ThinkingBlock raises
    "'ThinkingBlock' object has no attribute 'text'" — intermittently, because the
    model only sometimes thinks first. The ingestion service already hit this and
    iterates the blocks; RAG's LangChain path never got that treatment.

    Pinning langchain-anthropic <0.2.0 is load-bearing elsewhere (supervisor.py carries
    a monkeypatch for this exact version), so the fix is to bypass the wrapper for this
    one call rather than upgrade it.
    """
    from anthropic import AsyncAnthropic

    client_kwargs = {
        "api_key": settings.anthropic_auth_token or settings.anthropic_api_key,
        "default_headers": {"User-Agent": settings.anthropic_user_agent},
        "timeout": 25.0,
    }
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url

    text = prompt if isinstance(prompt, str) else str(prompt)
    response = await AsyncAnthropic(**client_kwargs).messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": text}],
    )

    # Take the first block that actually carries text; thinking blocks have none.
    answer = next(
        (b.text for b in response.content if getattr(b, "text", None)),
        "",
    )
    return _LLMResponse(answer, getattr(response, "usage", None))


async def _invoke_llm_with_retry(prompt, attempts: int = 2):
    """Gateway tail latency is erratic (measured 2.5s–110s for identical calls),
    so a timed-out or failed call is retried once before surfacing the error."""
    last_error = None
    for attempt in range(attempts):
        try:
            return await _invoke_via_sdk(prompt)
        except Exception as e:  # noqa: BLE001 — retry any transport/timeout failure
            last_error = e
            # NOTE: this module's logger is a stdlib logger, not structlog —
            # keyword fields raise "Logger._log() got an unexpected keyword
            # argument", which would mask the real failure behind a logging error.
            logger.warning(
                "LLM invoke failed (attempt %d/%d): %s", attempt + 1, attempts, e
            )
    raise last_error


async def generate_embedding(text: str) -> List[float]:
    """Generate 768-dimensional vector embedding for the input text."""
    response = await embedding_client.embeddings.create(
        model=settings.embedding_model,
        input=[text]
    )
    return response.data[0].embedding


# Fuzzy-match threshold for the FAQ short-circuit below, per the architecture doc's
# documented design ("A match above 0.85 similarity returns the FAQ answer directly").
FAQ_SIMILARITY_THRESHOLD = 0.85


async def _find_faq_match(question: str):
    """Fuzzy-matches `question` against faq_entries.question_pattern using pg_trgm's
    similarity() (extension already enabled by migration 005). Returns the
    best-matching row if it meets FAQ_SIMILARITY_THRESHOLD, else None."""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, answer_markdown, similarity(question_pattern, $1) AS sim
            FROM faq_entries
            ORDER BY sim DESC
            LIMIT 1
            """,
            question
        )
    if row and row["sim"] >= FAQ_SIMILARITY_THRESHOLD:
        return row
    return None


async def _record_faq_hit(faq_id) -> None:
    async with db.pool.acquire() as conn:
        await conn.execute(
            "UPDATE faq_entries SET hit_count = hit_count + 1 WHERE id = $1",
            faq_id
        )


async def query_rag(
    question: str, user_id: str, top_k: int = 5, trace: Any = None, flag_overrides: Dict[str, Any] | None = None
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Checks for a hand-curated FAQ match first (zero-token, skips the LLM entirely on
    a hit). Otherwise retrieves matching document chunks from the database, sends them
    with the question to Claude for answer generation, and records tracking metadata
    in Langfuse.
    """
    start_time = time.time()
    flags = flag_overrides or {}

    # 1. Compute question hash
    question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]

    # 1b. FAQ short-circuit -- a close match returns the curated answer directly,
    # without embedding the question, querying documents, or invoking the LLM.
    faq_match = await _find_faq_match(question)
    if faq_match:
        await _record_faq_hit(faq_match["id"])
        metrics_summary = {
            "question_hash": question_hash,
            "top_similarity": float(faq_match["sim"]),
            "chunks_retrieved": 0,
            "answer_tokens": 0,
            "latency_ms": (time.time() - start_time) * 1000,
            "faq_hit": True,
        }
        return faq_match["answer_markdown"], [], metrics_summary

    retrieval_span = None
    if trace is not None:
        try:
            retrieval_span = trace.start_observation(
                name="retrieval",
                as_type="retriever",
                input={"question": question, "top_k": top_k},
            )
        except Exception as exc:
            logger.warning("Failed to start Langfuse retrieval span: %s", exc)

    # 2. Embed the search query
    query_vector = await generate_embedding(question)

    # 3. Retrieve matching documents from pgvector database using Cosine Similarity
    retrieval_limit = flags.get("retrieval_width", getattr(settings, "rag_retrieval_width", 15))
    probes_val = flags.get("ivfflat_probes", getattr(settings, "rag_ivfflat_probes", 1))

    async with db.pool.acquire() as conn:
        # SET LOCAL is transaction-scoped. Outside a transaction Postgres discards it
        # with a warning, so this was a silent no-op and every query kept running at
        # the default probes=1 -- the exact ANN recall defect this ticket diagnosed.
        # Measured on this stack:
        #   no txn -> SHOW ivfflat.probes == ''    (discarded)
        #   in txn -> SHOW ivfflat.probes == '10'  (applied)
        # The retrieval query must run inside the same transaction to inherit it.
        async with conn.transaction():
            if probes_val > 1:
                await conn.execute(f"SET LOCAL ivfflat.probes = {int(probes_val)};")
            rows = await conn.fetch(
                """
                SELECT id, title, content, source_url,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM documents
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """,
                query_vector,
                retrieval_limit,
            )
    sources = [
        {
            "id": str(row["id"]),
            "title": row.get("title"),
            "content": row["content"],
            "source_url": row["source_url"],
            "similarity": float(row["similarity"]),
            "relevance_score": float(row["similarity"]),
        }
        for row in rows
    ]
    top_similarity = max([s["similarity"] for s in sources], default=0.0)

    # Confidence Threshold Check BEFORE LLM invocation (gated by flag)
    threshold_enabled = flags.get("threshold_enabled", getattr(settings, "rag_threshold_enabled", True))
    CONFIDENCE_THRESHOLD = getattr(settings, "confidence_threshold", 0.60)

    if threshold_enabled and top_similarity < CONFIDENCE_THRESHOLD:
        from app.core.metrics import LOW_CONFIDENCE_TOTAL
        LOW_CONFIDENCE_TOTAL.inc()
        total_latency_ms = (time.time() - start_time) * 1000
        metrics_summary = {
            "question_hash": question_hash,
            "top_similarity": top_similarity,
            "chunks_retrieved": len(sources),
            "answer_tokens": 0,
            "latency_ms": total_latency_ms,
            "refused": True,
            "refusal_reason": "insufficient_data",
            "refusal_suggestion": "Please rephrase your question with specific details regarding universities, programs, or visa requirements.",
        }
        return None, sources[:top_k], metrics_summary

    # Step 6: Cross-Encoder Re-Ranking (gated by flag)
    rerank_enabled = flags.get("rerank_enabled", getattr(settings, "rag_rerank_enabled", True))
    if rerank_enabled:
        from app.services.reranker import Reranker
        reranker = Reranker()
        sources = reranker.rank(question, sources, top_n=top_k)
    else:
        sources = sources[:top_k]

    # Eval affordance (see api/query.py). Retrieval is complete and re-ranked at this
    # point, so the retrieval metrics are fully determined; stopping here lets the
    # benchmark measure ranking without depending on LLM availability.
    if flags.get("retrieval_only"):
        metrics_summary = {
            "question_hash": question_hash,
            "top_similarity": top_similarity,
            "chunks_retrieved": len(sources),
            "answer_tokens": 0,
            "latency_ms": (time.time() - start_time) * 1000,
            "retrieval_only": True,
        }
        return None, sources, metrics_summary

    if retrieval_span is not None:
        try:
            retrieval_span.update(
                output=sources,
                metadata={"top_k": top_k, "top_similarity": top_similarity},
            )
            retrieval_span.end()
        except Exception as exc:
            logger.warning("Failed to end Langfuse retrieval span: %s", exc)


    # 4. Format context for prompt
    context_str = "\n\n".join(
        [
            f"Source: {s['source_url'] or 'Unknown'}\nContent: {s['content']}"
            for s in sources
        ]
    )

    prompt = f"""You are a helpful assistant. Use the following context to answer the user's question. If the answer cannot be found in the context, say that you do not know.

Context:
{context_str}

Question:
{question}

Answer:"""

    # 5. Call LLM (Claude)
    generation = None
    if trace is not None:
        try:
            generation = trace.start_observation(
                name="answer-generation",
                as_type="generation",
                model=settings.llm_model,
                input=prompt,
            )
        except Exception as exc:
            logger.warning("Failed to start Langfuse generation: %s", exc)

    response = await _invoke_llm_with_retry(prompt)
    answer_text = response.content

    # Extract token usage
    token_usage = response.response_metadata.get("usage", {})
    if hasattr(token_usage, "input_tokens"):
        input_tokens = getattr(token_usage, "input_tokens", 0)
        output_tokens = getattr(token_usage, "output_tokens", 0)
    else:
        input_tokens = token_usage.get("input_tokens", 0) if isinstance(token_usage, dict) else 0
        output_tokens = token_usage.get("output_tokens", 0) if isinstance(token_usage, dict) else 0

    # Estimated cost calculation for claude-haiku-4-5-20251001 ($0.25/M input, $1.25/M output tokens)
    cost_usd = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000

    if generation is not None:
        try:
            generation.update(
                output=answer_text,
                usage_details={
                    "input": int(input_tokens),
                    "output": int(output_tokens),
                },
                metadata={
                    "cost_usd": cost_usd,
                    "chunks_used": len(sources),
                },
            )
            generation.end()
        except Exception as exc:
            logger.warning("Failed to end Langfuse generation: %s", exc)
    
    try:
        from app.telemetry import record_llm_cost
        record_llm_cost(user_id, settings.llm_model, input_tokens, output_tokens)
    except ImportError:
        logger.warning("telemetry helper not found")

    total_latency_ms = (time.time() - start_time) * 1000

    metrics_summary = {
        "question_hash": question_hash,
        "top_similarity": top_similarity,
        "chunks_retrieved": len(sources),
        "answer_tokens": output_tokens,
        "latency_ms": total_latency_ms,
    }

    return answer_text, sources, metrics_summary
