import httpx
from typing import Any
from uuid import UUID


class SpeakingServiceClient:
    def __init__(self, base_url, internal_api_key: str):
        self.base_url = base_url
        self.internal_api_key = internal_api_key

    async def evaluate_holistic(
        self, session_id: UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"x-Internal-Api-Key": self.internal_api_key},
            timeout=30.0,
        ) as client:
            response = await client.post(
                url="/internal/evaluate/holistic",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
