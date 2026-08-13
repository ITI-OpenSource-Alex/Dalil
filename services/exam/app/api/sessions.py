from typing import Any
from uuid import UUID
from fastapi import Header

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends

from app.core.database import db
from app.core.metrics import goa_exam_sessions_total
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.schemas import CreateSessionRequest, SubmitAnswersRequest
from app.services.session_service import SessionService
from app.services.writing_image_delivery_service import S3WritingImageDeliveryService
from app.repositories.writing_response_repository import WritingResponseRepository
from app.services.writing_client import WritingClient
from app.core.config import settings

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_image_delivery_service() -> S3WritingImageDeliveryService:
    # Sign against the PUBLIC endpoint, not the internal one. SigV4 signs the
    # Host header, so a URL signed against http://localstack:4566 is invalid the
    # moment a browser (which cannot resolve that host) requests it -- the
    # BUG-016 failure. s3_public_endpoint_url is the browser-reachable host;
    # falls back to the internal endpoint when unset so tests are unaffected.
    presign_endpoint = settings.s3_public_endpoint_url or settings.aws_endpoint_url
    s3_client = boto3.client(
        "s3",
        region_name=settings.s3_region or settings.aws_region,
        endpoint_url=presign_endpoint,
        config=Config(signature_version="s3v4"),
    )
    return S3WritingImageDeliveryService(
        s3_client=s3_client,
        bucket=settings.writing_image_bucket,
    )


def get_session_service(
    image_delivery_service: S3WritingImageDeliveryService = Depends(
        get_image_delivery_service
    ),
) -> SessionService:
    return SessionService(
        session_repository=SessionRepository(db.pool),
        question_repository=QuestionRepository(db.pool),
        result_repository=ResultRepository(db.pool),
        writing_response_repository=WritingResponseRepository(db.pool),
        writing_client=WritingClient(base_url=settings.writing_service_url),
        image_delivery_service=image_delivery_service,
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
    x_user_id: UUID = Header(),
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    return await service.get_result(session_id, requester_id=x_user_id)
