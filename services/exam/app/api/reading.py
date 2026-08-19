import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.database import db
from app.core.metrics import (
    goa_exam_grading_latency_ms,
    goa_exam_reading_score,
    goa_exam_reading_sessions_total,
)
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.common import ExamType
from app.schemas.reading import ReadingSubmitRequest
from app.services.session_service import SessionService

router = APIRouter(
    prefix="/exam/reading",
    tags=["reading"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_session_service() -> SessionService:
    return SessionService(
        session_repository=SessionRepository(db.pool),
        question_repository=QuestionRepository(db.pool),
        result_repository=ResultRepository(db.pool),
    )


@router.get("/start")
async def start_reading_exam(
    exam_type: ExamType = Query(...),
    user_id: UUID = Query(...),
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    result = await service.create_reading_session(
        user_id=user_id,
        exam_type=exam_type.value,
    )
    goa_exam_reading_sessions_total.labels(exam_type=exam_type.value).inc()
    return result


@router.put("/{session_id}/submit")
async def submit_reading_exam(
    session_id: UUID,
    request: ReadingSubmitRequest,
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    start = time.perf_counter()
    result = await service.submit_reading_session(
        session_id=session_id,
        answers=request.answers,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    goa_exam_grading_latency_ms.labels(skill_area="reading").observe(elapsed_ms)
    goa_exam_reading_score.observe(result["band_score"])
    return result
