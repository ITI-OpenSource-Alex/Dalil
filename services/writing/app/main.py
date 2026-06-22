from fastapi import FastAPI
from fastapi import Form
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Essay

app = FastAPI(
    title="GOA Writing Service",
    version="1.0.0"
)


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
    db: Session = Depends(get_db)
):
    essay = Essay(
    user_id=userId,
    extracted_text=essayText,
    submission_type=submissionType,
    exam_session_id=examSessionId,
    status="pending"
)

    db.add(essay)
    db.commit()
    db.refresh(essay)

    return {
        "id": essay.id,
        "status": essay.status
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