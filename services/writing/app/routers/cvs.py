import logging
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.dependencies import get_db, get_s3_client, get_sqs_client
from app.models import CVReview
from app.schemas import CVReviewRequest, CVUploadResponse
from app.services.cv_review import review_cv
from app.services.cv_storage import (
    content_sha256,
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
        413: {"description": "CV exceeds 10 MB"},
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
    content_hash = content_sha256(file)
    s3_key = make_s3_key(userId, extension)
    review = CVReview(
        user_id=userId,
        s3_key=s3_key,
        original_filename=original_filename,
        status="processing",
        content_hash=content_hash,
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
        upload_to_s3(
            s3_client,
            file,
            settings.s3_bucket,
            s3_key,
            content_hash=content_hash,
        )
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


@router.post(
    "/review",
    summary="Review an extracted CV",
)
async def review_cv_endpoint(
    payload: CVReviewRequest,
    db: Session = Depends(get_db),
):
    """Turn an extracted CV into actionable feedback."""
    validate_user_id(payload.userId)

    review = db.query(CVReview).filter(CVReview.s3_key == payload.cvS3Key).first()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV not found",
        )

    if review.user_id != payload.userId:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CV belongs to another user",
        )

    if review.status != "ready":
        # 409, not 500: nothing is broken, the extraction simply has not
        # finished. A CV that failed extraction reports its own error rather
        # than being reviewed on empty text -- reviewing nothing would produce
        # confident feedback about a document the model never saw.
        detail = (
            f"CV extraction failed: {review.error_message}"
            if review.status == "failed" and review.error_message
            else f"CV is not ready for review (status: {review.status})"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    if not review.extracted_text and not review.structured_data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CV is marked ready but holds no extracted content",
        )

    try:
        execution = await review_cv(
            review.extracted_text,
            review.structured_data,
            payload.targetCountry,
            payload.targetField,
        )
    except Exception as exc:
        logger.exception("CV review failed", extra={"cv_s3_key": payload.cvS3Key})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The CV review model could not be reached",
        ) from exc

    response_payload = execution.review.model_dump()

    async def event_stream():
        for section in response_payload["sections"]:
            yield (
                "event: section\n"
                f"data: {json.dumps(section, separators=(',', ':'))}\n\n"
            )
        yield (
            "event: complete\n"
            f"data: {json.dumps(response_payload, separators=(',', ':'))}\n\n"
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
