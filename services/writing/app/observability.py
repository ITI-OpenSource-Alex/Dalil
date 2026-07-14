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
