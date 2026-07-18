import json
import logging
from functools import lru_cache
from typing import Any

from app.config import get_settings


logger = logging.getLogger("writing.evaluation")


@lru_cache
def get_langfuse_client() -> Any:
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def start_evaluation_trace(
    client: Any,
    *,
    user_id: str,
    essay_id: int,
    task_type: str,
    from_cache: bool,
) -> Any:
    if client is None:
        return None
    try:
        return client.trace(
            name="writing-evaluation-swarm",
            user_id=user_id,
            metadata={
                "user_id": user_id,
                "essay_id": essay_id,
                "task_type": task_type,
                "from_cache": from_cache,
            },
        )
    except Exception as exc:
        logger.warning("Unable to create Langfuse writing trace: %s", exc)
        return None


def log_evaluation(
    *,
    user_id: str,
    essay_id: int,
    bands: dict[str, float],
    overall_band: float,
    latency_ms: float,
    from_cache: bool,
    total_tokens: int,
    total_cost_usd: float,
) -> None:
    logger.info(
        json.dumps(
            {
                "user_id": user_id,
                "essay_id": essay_id,
                "bands": bands,
                "overall_band": overall_band,
                "latency_ms": round(latency_ms, 2),
                "from_cache": from_cache,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost_usd, 8),
            },
            separators=(",", ":"),
        )
    )


def trace_cv_extraction(
    client: Any,
    *,
    user_id: str,
    cv_id: int,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    cost_usd: float,
    fields_extracted: int,
) -> None:
    """Record CV extraction metadata without sending the CV text to Langfuse."""
    if client is None:
        return
    try:
        trace = client.trace(
            name="cv-structured-extraction",
            user_id=user_id,
            metadata={"cv_id": cv_id},
        )
        generation = trace.generation(
            name="extract-structured-cv-fields",
            model=model,
            input={"cv_id": cv_id, "content": "redacted"},
        )
        generation.end(
            output={"fields_extracted": fields_extracted},
            usage={"input": input_tokens, "output": output_tokens},
            metadata={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": round(latency_ms, 2),
                "cost_usd": round(cost_usd, 8),
                "fields_extracted": fields_extracted,
            },
        )
        flush = getattr(client, "flush", None)
        if flush:
            flush()
    except Exception as exc:
        logger.warning("Unable to record Langfuse CV extraction trace: %s", exc)
