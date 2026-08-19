import base64
import os
from datetime import datetime, timezone

import redis
import structlog


logger = structlog.get_logger(__name__)
SERVICE_NAME = "writing"
RETENTION_SECONDS = 35 * 24 * 60 * 60
_redis_client = None


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _encoded_model(model: str) -> str:
    return base64.urlsafe_b64encode(
        (model or "unknown").encode("utf-8")
    ).decode("ascii").rstrip("=")


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get(
            "REDIS_GATEWAY_URL", "redis://redis-gateway:6379/0"
        )
        _redis_client = redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


def record_llm_cost(
    user_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    if input_tokens <= 0 and output_tokens <= 0:
        return

    try:
        date = _utc_date()
        encoded_model = _encoded_model(model)
        keys = (
            f"llm:tokens:{date}:user:{user_id}:{SERVICE_NAME}",
            f"llm:tokens:{date}:global",
            (
                f"llm:tokens:{date}:user:{user_id}:{SERVICE_NAME}"
                f":model:{encoded_model}"
            ),
            f"llm:tokens:{date}:global:model:{encoded_model}",
        )
        pipeline = _get_redis_client().pipeline(transaction=False)
        for key in keys:
            if input_tokens > 0:
                pipeline.hincrby(key, "input", input_tokens)
            if output_tokens > 0:
                pipeline.hincrby(key, "output", output_tokens)
            pipeline.expire(key, RETENTION_SECONDS, nx=True)
        pipeline.execute()
    except Exception as exc:
        logger.error("failed_to_record_telemetry", error=str(exc))
