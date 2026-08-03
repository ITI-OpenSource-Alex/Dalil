import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.dependencies import get_db, get_s3_client, get_sqs_client
from app.models import CVReview
from app.schemas import CVReviewRequest, CVUploadResponse
from app.services.cv_review import (
    CVReviewCoordinator,
    cv_review_cache_key,
    cv_review_response,
    fetch_country_conventions,
    get_cached_review,
    get_cv_review_coordinator,
    get_redis_client,
    set_cached_review,
)
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
    response_model=None,
    summary="Review an extracted CV",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def review_cv_endpoint(
    payload: CVReviewRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    coordinator: CVReviewCoordinator = Depends(get_cv_review_coordinator),
):
    """Stream a structured CV review from already-extracted CV content."""
    validate_user_id(payload.userId)

    review = (
        db.query(CVReview)
        .filter(CVReview.user_id == payload.userId, CVReview.s3_key == payload.cvS3Key)
        .first()
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV not found",
        )

    if review.status != "ready":
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

    cache_key = cv_review_cache_key(
        review.extracted_text or "",
        payload.targetCountry,
        payload.targetField,
        settings,
    )
    cache_client = get_redis_client(settings)
    try:
        cached_payload = await get_cached_review(cache_client, cache_key)
    except Exception:
        logger.warning("CV review cache read failed", exc_info=True)
        cached_payload = None

    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def on_partial(section):
            await queue.put(("section", section.model_dump(mode="json")))

        async def review_in_background():
            try:
                if cached_payload is not None:
                    summary = await coordinator.replay_cached(
                        cached_payload,
                        on_partial=on_partial,
                    )
                    from_cache = True
                else:
                    conventions = await fetch_country_conventions(
                        payload.userId,
                        payload.targetCountry,
                        settings,
                    )
                    summary = await coordinator.review(
                        extracted_text=review.extracted_text,
                        structured_data=review.structured_data,
                        target_country=payload.targetCountry,
                        target_field=payload.targetField,
                        country_conventions=conventions,
                        on_partial=on_partial,
                    )
                    from_cache = False
                    try:
                        await set_cached_review(
                            cache_client,
                            cache_key,
                            cv_review_response(summary).model_dump(mode="json"),
                        )
                    except Exception:
                        logger.warning("CV review cache write failed", exc_info=True)

                data = cv_review_response(summary).model_dump(mode="json")
                data["fromCache"] = from_cache
                await queue.put(("complete", data))
            except Exception:
                logger.exception("CV review failed", extra={"cv_id": review.id})
                await queue.put(
                    ("error", {"detail": "The CV review model could not be reached"})
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(review_in_background())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                event_name, data = event
                yield (
                    f"event: {event_name}\n"
                    f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
                )
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
