from uuid import UUID

from fastapi import Header, Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

from app.core.config import settings

API_KEY_NAME = 'X-Internal-API-Key'
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(header_key: str = Security(api_key_header)):
    if not header_key or header_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Api-Key header"
        )
    return header_key


async def require_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    """Ownership dependency for user-facing endpoints (GOA-084: checklists).

    Unlike the internal routes above, these endpoints take no API key -- ownership
    is scoped entirely by this header, matching the exam service's heartbeat pattern.
    Validated as UUID-shaped then handed back as str: local_user_profiles.user_id is
    a UUID column but every RAG service call site (scoring.py, profile_repo.py)
    already passes user ids around as plain strings, and asyncpg accepts str for
    UUID columns/parameters.
    """
    try:
        UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-User-ID header must be a valid UUID",
        )
    return x_user_id
