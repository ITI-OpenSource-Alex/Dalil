import os
import structlog
from redis.asyncio import Redis, from_url


logger = structlog.get_logger("rag_service.redis")


class RedisClient:
    def __init__(self):
        self.redis: Redis | None = None

    async def connect(self):
        url = os.getenv("REDIS_URL", "redis://localhost:6379/2")
        self.redis = from_url(url, decode_responses=True)
        await self.redis.ping()
        logger.info("Connected to Redis for RAG cache.")

    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis.")


redis_client = RedisClient()
