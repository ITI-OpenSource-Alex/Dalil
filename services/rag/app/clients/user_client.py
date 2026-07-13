import os
import httpx
import structlog
from typing import AsyncGenerator

logger = structlog.get_logger("rag_service.user_client")


class UserServiceUnavailable(Exception):
    pass


async def get_all_users(limit: int = 50) -> AsyncGenerator[list[dict], None]:
    """
    Paginates through the User service's internal bulk endpoint.
    Yields batches (lists) of user profiles.
    """
    base_url = os.getenv("USER_SERVICE_URL", "http://user-service:8081")
    api_key = os.getenv(
        "INTERNAL_API_KEY", "dev-internal-key"
    )  # Ensure this matches your dev env
    headers = {"x-internal-api-key": api_key}

    page = 1
    has_more = True

    async with httpx.AsyncClient() as client:
        while has_more:
            url = f"{base_url}/users/internal?page={page}&limit={limit}"

            try:
                # 10s timeout since bulk queries can be slightly heavier
                response = await client.get(url, headers=headers, timeout=10.0)
                response.raise_for_status()

                data = response.json()
                users = data.get("users", [])
                has_more = data.get("hasMore", False)

                if users:
                    yield users

                page += 1

            except httpx.RequestError as e:
                logger.error(
                    f"Connection to User Service failed during backfill: {str(e)}"
                )
                raise UserServiceUnavailable("User Service is currently unavailable.")
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"User service returned HTTP {e.response.status_code} during backfill"
                )
                raise UserServiceUnavailable(
                    f"User service HTTP error: {e.response.status_code}"
                )
