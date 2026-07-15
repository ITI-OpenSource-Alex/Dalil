from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.database import db
from app.core.metrics import goa_exam_sessions_total
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.schemas import CreateSessionRequest, SubmitAnswersRequest
from app.services.session_service import SessionService

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_session_service() -> SessionService:
    return SessionService(
        session_repository=SessionRepository(db.pool),
        question_repository=QuestionRepository(db.pool),
        result_repository=ResultRepository(db.pool),
    )


@router.post("")
async def create_session(
    request: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    return await service.create_session(request)


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    session = await service.get_session(session_id)
    session["remaining_time_seconds"] = session.pop("remaining_seconds")
    return session


@router.put("/{session_id}/submit")
async def submit_session(
    session_id: UUID,
    request: SubmitAnswersRequest,
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    session = await service.get_session(session_id)
    result = await service.submit_session(session_id, request)
    goa_exam_sessions_total.labels(
        skill_area=session["skill_area"],
        exam_type=session["exam_type"],
        outcome="completed",
    ).inc()
    return result


@router.get("/{session_id}/result")
async def get_result(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    return await service.get_result(session_id)
