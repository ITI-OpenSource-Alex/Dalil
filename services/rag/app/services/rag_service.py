import hashlib
import time
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Any

from langchain_openai import OpenAIEmbeddings
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

openai_key = settings.openai_api_key or "mock-key"
anthropic_key = settings.anthropic_api_key or "mock-key"

embeddings_model = OpenAIEmbeddings(
    model="text-embedding-3-small", openai_api_key=openai_key
)

llm = ChatAnthropic(model="claude-haiku-4-5-20251001", anthropic_api_key=anthropic_key)


async def generate_embedding(text: str) -> List[float]:
    """Generate 1536-dimensional vector embedding for the input text."""
    return await embeddings_model.aembed_query(text)


async def query_rag(
    question: str, user_id: str, top_k: int = 5
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Retrieves matching document chunks from the database, sends them with the question
    to Claude for answer generation, and records tracking metadata in Langfuse.
    """
    start_time = time.time()

    # 1. Compute question hash
    question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]

    # 2. Embed the search query
    query_vector = await generate_embedding(question)

    # 3. Retrieve matching documents from pgvector database using Cosine Similarity
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, content, source_url,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM documents
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """,
            query_vector,
            top_k,
        )

    sources = []
    top_similarity = 0.0
    for row in rows:
        sim = float(row["similarity"])
        sources.append(
            {
                "id": str(row["id"]),
                "content": row["content"],
                "source_url": row["source_url"],
                "similarity": sim,
            }
        )
        if sim > top_similarity:
            top_similarity = sim

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
    llm_start_time = time.time()
    response = await llm.ainvoke(prompt)
    llm_latency_ms = (time.time() - llm_start_time) * 1000
    answer_text = response.content

    # Extract token usage
    token_usage = response.response_metadata.get("usage", {})
    input_tokens = token_usage.get("input_tokens", 0)
    output_tokens = token_usage.get("output_tokens", 0)

    # Estimated cost calculation for claude-haiku-4-5-20251001 ($0.25/M input, $1.25/M output tokens)
    cost_usd = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000

    total_latency_ms = (time.time() - start_time) * 1000

    # 6. Trace in Langfuse
    if langfuse_client:
        try:
            trace = langfuse_client.trace(
                name="rag-query",
                user_id=user_id,
                metadata={
                    "question_hash": question_hash,
                    "top_similarity_score": top_similarity,
                },
            )

            trace.span(
                name="retrieval",
                start_time=datetime.fromtimestamp(start_time),
                end_time=datetime.fromtimestamp(
                    start_time + (total_latency_ms - llm_latency_ms) / 1000
                ),
                input=question,
                output=sources,
                metadata={"top_k": top_k, "top_similarity": top_similarity},
            )

            trace.generation(
                name="answer-generation",
                model="claude-haiku-4-5-20251001",
                start_time=datetime.fromtimestamp(
                    start_time + (total_latency_ms - llm_latency_ms) / 1000
                ),
                end_time=datetime.fromtimestamp(time.time()),
                input=prompt,
                output=answer_text,
                usage={"input": input_tokens, "output": output_tokens},
                metadata={"cost_usd": cost_usd, "chunks_used": len(sources)},
            )
        except Exception as e:
            logger.error("Failed to write trace to Langfuse: %s", str(e))

    metrics_summary = {
        "question_hash": question_hash,
        "top_similarity": top_similarity,
        "chunks_retrieved": len(sources),
        "answer_tokens": output_tokens,
        "latency_ms": total_latency_ms,
    }

    return answer_text, sources, metrics_summary
