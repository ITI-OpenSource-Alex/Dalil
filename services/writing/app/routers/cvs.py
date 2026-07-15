import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.dependencies import get_db, get_s3_client, get_sqs_client
from app.models import CVReview
from app.schemas import CVUploadResponse
from app.services.cv_storage import (
    delete_from_s3,
    make_s3_key,
    upload_to_s3,
    validate_upload,
    validate_user_id,
)
from app.services.event_publisher import publish_cv_uploaded


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cv", tags=["CV"])


def _delete_review(db: Session, review: CVReview) -> None:
    try:
        db.delete(review)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to remove compensated CV review", extra={"cv_id": review.id})


def _delete_object(s3_client, bucket: str, key: str) -> None:
    try:
        delete_from_s3(s3_client, bucket, key)
    except Exception:
        logger.exception("Failed to remove compensated CV object", extra={"s3_key": key})


@router.post(
    "/upload",
    response_model=CVUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"description": "CV exceeds 10 MB"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "Unsupported CV format"},
    },
)
async def upload_cv(
    request: Request,
    userId: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    s3_client=Depends(get_s3_client),
    sqs_client=Depends(get_sqs_client),
    settings: Settings = Depends(get_settings),
) -> CVUploadResponse:
    validate_user_id(userId)
    extension, original_filename = await validate_upload(file)
    s3_key = make_s3_key(userId, extension)
    review = CVReview(
        user_id=userId,
        s3_key=s3_key,
        original_filename=original_filename,
        status="processing",
    )

    try:
        db.add(review)
        db.commit()
        db.refresh(review)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create CV review")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not record the CV upload",
        ) from exc

    try:
        upload_to_s3(s3_client, file, settings.s3_bucket, s3_key)
    except Exception as exc:
        _delete_review(db, review)
        logger.exception("Failed to store CV", extra={"s3_key": s3_key})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not store the CV",
        ) from exc

    correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
    try:
        publish_cv_uploaded(
            sqs_client=sqs_client,
            queue_url=settings.cv_uploaded_queue_url,
            user_id=userId,
            s3_key=s3_key,
            file_name=original_filename,
            correlation_id=correlation_id,
        )
    except Exception as exc:
        _delete_object(s3_client, settings.s3_bucket, s3_key)
        _delete_review(db, review)
        logger.exception("Failed to publish CV upload event", extra={"s3_key": s3_key})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not publish the CV upload event",
        ) from exc

    return CVUploadResponse(cvId=review.id, status=review.status)
