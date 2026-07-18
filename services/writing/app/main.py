from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

from app.routers import internal
from app.config import MAX_CV_REQUEST_BYTES
from app.dependencies import get_db
from app.models import Essay
from app.routers.cvs import router as cv_router
from app.routers.essays import router as essay_router

app = FastAPI(
    title="GOA Writing Service",
    version="1.0.0"
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


@app.middleware("http")
async def reject_oversized_cv_request(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/cv/upload":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_CV_REQUEST_BYTES:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"detail": "CV files must be 10 MB or smaller"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid Content-Length header"},
                )
    return await call_next(request)


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
