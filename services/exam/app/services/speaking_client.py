import httpx
from typing import Any
from uuid import UUID

from app.core.config import settings


class SpeakingServiceClient:
    def __init__(self, base_url, internal_api_key: str, timeout_s: float | None = None):
        self.base_url = base_url
        self.internal_api_key = internal_api_key
        # Sourced from settings rather than hardcoded, so the outer-must-exceed-inner
        # invariant with the speaking service's swarm budget is expressed in one
        # place and testable. See config.speaking_evaluation_timeout_s.
        self.timeout_s = (
            timeout_s if timeout_s is not None else settings.speaking_evaluation_timeout_s
        )

    async def evaluate_holistic(
        self, session_id: UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"x-Internal-Api-Key": self.internal_api_key},
            timeout=self.timeout_s,
        ) as client:
            response = await client.post(
                url="/internal/evaluate/holistic",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
