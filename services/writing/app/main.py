from pathlib import Path

from fastapi import FastAPI
from fastapi import Form
from fastapi import Depends
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi import File
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Essay

app = FastAPI(
    title="GOA Writing Service",
    version="1.0.0"
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


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
        "examSessionId": essay.exam_session_id
    }