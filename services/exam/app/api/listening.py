import time
from typing import Any
from uuid import UUID

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.database import db
from app.core.metrics import (
    goa_exam_grading_latency_ms,
    goa_exam_listening_score,
    goa_exam_listening_sessions_total,
)
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.common import ExamType
from app.schemas.listening import ListeningSubmitRequest
from app.services.audio_delivery_service import S3AudioDeliveryService
from app.services.session_service import SessionService
from app.services.writing_image_delivery_service import S3WritingImageDeliveryService


router = APIRouter(
    prefix="/exam/listening",
    tags=["listening"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_audio_delivery_service() -> S3AudioDeliveryService:
    presign_endpoint = settings.s3_public_endpoint_url or settings.aws_endpoint_url
    s3_client = boto3.client(
        "s3",
        region_name=settings.s3_region or settings.aws_region,
        endpoint_url=presign_endpoint,
        config=Config(signature_version="s3v4"),
    )
    head_client = boto3.client(
        "s3",
        region_name=settings.s3_region or settings.aws_region,
        endpoint_url=settings.aws_endpoint_url or presign_endpoint,
        config=Config(signature_version="s3v4"),
    )
    return S3AudioDeliveryService(
        s3_client=s3_client,
        bucket=settings.s3_bucket,
        head_client=head_client,
    )


def get_image_delivery_service() -> S3WritingImageDeliveryService:
    presign_endpoint = settings.s3_public_endpoint_url or settings.aws_endpoint_url
    s3_client = boto3.client(
        "s3",
        region_name=settings.s3_region or settings.aws_region,
        endpoint_url=presign_endpoint,
        config=Config(signature_version="s3v4"),
    )
    head_client = boto3.client(
        "s3",
        region_name=settings.s3_region or settings.aws_region,
        endpoint_url=settings.aws_endpoint_url or presign_endpoint,
        config=Config(signature_version="s3v4"),
    )
    return S3WritingImageDeliveryService(
        s3_client=s3_client,
        bucket=settings.writing_image_bucket,
        head_client=head_client,
    )


def get_session_service(
    audio_delivery_service: S3AudioDeliveryService = Depends(
        get_audio_delivery_service
    ),
    image_delivery_service: S3WritingImageDeliveryService = Depends(
        get_image_delivery_service
    ),
) -> SessionService:
    return SessionService(
        session_repository=SessionRepository(db.pool),
        question_repository=QuestionRepository(db.pool),
        result_repository=ResultRepository(db.pool),
        audio_delivery_service=audio_delivery_service,
        image_delivery_service=image_delivery_service,
    )


@router.get("/start")
async def start_listening_exam(
    user_id: UUID = Query(...),
    exam_type: ExamType = Query(default=ExamType.ACADEMIC),
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    result = await service.create_listening_session(
        user_id=user_id,
        exam_type=exam_type.value,
    )
    goa_exam_listening_sessions_total.labels(exam_type=exam_type.value).inc()
    return result


@router.put("/{session_id}/submit")
async def submit_listening_exam(
    session_id: UUID,
    request: ListeningSubmitRequest,
    user_id: UUID = Query(...),
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    start = time.perf_counter()
    result = await service.submit_listening_session(
        session_id=session_id,
        user_id=user_id,
        answers=request.answers,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    goa_exam_grading_latency_ms.labels(skill_area="listening").observe(elapsed_ms)
    goa_exam_listening_score.observe(result["band_score"])
    return result
