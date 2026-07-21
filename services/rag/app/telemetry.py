import os
import redis
import structlog

logger = structlog.get_logger(__name__)

def record_llm_cost(user_id: str, model: str, input_tokens: int, output_tokens: int):
    try:
        redis_url = os.environ.get("REDIS_GATEWAY_URL", "redis://redis-gateway:6379/0")
        r = redis.from_url(redis_url)
        
        # We store tokens. The gateway will convert them to USD.
        if input_tokens:
            r.hincrby(f"llm:tokens:user:{user_id}", "input", int(input_tokens))
            r.hincrby("llm:tokens:global", "input", int(input_tokens))
        if output_tokens:
            r.hincrby(f"llm:tokens:user:{user_id}", "output", int(output_tokens))
            r.hincrby("llm:tokens:global", "output", int(output_tokens))
    except Exception as e:
        logger.error("failed_to_record_telemetry", error=str(e))
