from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.exceptions import HTTPException

from app.core.database import db
from app.core.security import validate_internal_api_key
from app.repositories.heartbeat_repository import HeartbeatRepository

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_heartbeat_repo() -> HeartbeatRepository:
    return HeartbeatRepository(db.pool)


@router.patch("/{session_id}/heartbeat", status_code=204)
async def session_heartbeat(
    session_id: UUID,
    x_user_id: UUID = Header(),
    repo: HeartbeatRepository = Depends(get_heartbeat_repo),
) -> Response:
    session = await repo.get_session_for_heartbeat(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if str(session["user_id"]) != str(x_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session belongs to another user",
        )

    if session["status"] in ("submitted", "scored"):
        return Response(status_code=204)

    await repo.touch_heartbeat(session_id)
    return Response(status_code=204)
