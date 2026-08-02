import asyncio
import time
from pathlib import Path

import structlog

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

from app.core.logging import configure_logging, correlation_id_var
from app.routers import internal
from app.config import MAX_CV_REQUEST_BYTES
from app.dependencies import get_db
from app.models import Essay
from app.routers.cvs import router as cv_router
from app.routers.essays import router as essay_router
from app.services.account_deletion_consumer import consume_account_deleted_messages

configure_logging()
logger = structlog.get_logger("writing_service.main")

app = FastAPI(
    title="GOA Writing Service",
    version="1.0.0"
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Bind the incoming correlation ID and log one line per request.

    The gateway forwards X-Correlation-Id on every downstream call and it
    reached this service correctly all along -- but nothing here logged a
    structured line, so the ID arrived and was never written down. Requests
    showed up only in uvicorn's access log, which has no correlation field,
    making a request untraceable across services (BUG-030).
    """
    correlation_id = request.headers.get("X-Correlation-Id")
    token = None
    if correlation_id:
        # Reset in `finally`: leaving it set means the next request without a
        # header inherits this one's ID and logs it as if it were its own.
        token = correlation_id_var.set(correlation_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return response
    except Exception:
        logger.exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        raise
    finally:
        if token is not None:
            correlation_id_var.reset(token)


@app.middleware("http")
async def reject_oversized_cv_request(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/cv/upload":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_CV_REQUEST_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "CV files must be 10 MB or smaller"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid Content-Length header"},
                )
    return await call_next(request)



@app.on_event("startup")
async def start_account_deleted_consumer():
    app.state.account_deleted_consumer = asyncio.create_task(consume_account_deleted_messages())


@app.on_event("shutdown")
async def stop_account_deleted_consumer():
    task = getattr(app.state, "account_deleted_consumer", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/essays/upload")
def upload_essay(
    userId: str = Form(...),
    essayText: str = Form(...),
    submissionType: str = Form(...),
    examSessionId: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    s3_key = None

    if file:
        extension = Path(file.filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail="Unsupported file type"
            )

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 10MB limit"
            )

        s3_key = f"uploads/{userId}/{file.filename}"

    essay = Essay(
        user_id=userId,
        s3_key=s3_key,
        extracted_text=essayText,
        submission_type=submissionType,
        exam_session_id=examSessionId,
        status="ready"
    )

    db.add(essay)
    db.commit()
    db.refresh(essay)

    return {
        "id": essay.id,
        "status": essay.status,
        "s3Key": essay.s3_key
    }


@app.get("/essays/{essay_id}")
def get_essay(
    essay_id: int,
    db: Session = Depends(get_db)
):
    essay = (
        db.query(Essay)
        .filter(Essay.id == essay_id)
        .first()
    )

    if not essay:
        raise HTTPException(
            status_code=404,
            detail="Essay not found"
        )

    return {
        "id": essay.id,
        "userId": essay.user_id,
        "s3Key": essay.s3_key,
        "extractedText": essay.extracted_text,
        "uploadedAt": essay.uploaded_at,
        "status": essay.status,
        "submissionType": essay.submission_type,
        "examSessionId": essay.exam_session_id,
        "examType": essay.exam_type,
        "evaluationResult": essay.evaluation_result,
    }


app.include_router(internal.router)
app.include_router(cv_router)
app.include_router(essay_router)

