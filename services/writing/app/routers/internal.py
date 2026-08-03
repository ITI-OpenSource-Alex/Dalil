import os
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError


from app.database import SessionLocal
from app.models import CVReview, Essay
from app.services.account_deletion import purge_user_data

router = APIRouter(prefix="/internal")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

    
@router.get("/cv-text/{userId}")
def get_cv_text(userId: str, 
    x_internal_api_key: str = Header(None),
    db: Session = Depends(get_db)
    ):
    expected_key = os.getenv("INTERNAL_API_KEY")
    if not expected_key or x_internal_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid Internal API Key")

    try:
        query = text("""
            SELECT extracted_text 
            FROM cv_reviews 
            WHERE user_id = :user_id AND status = 'ready' 
            ORDER BY uploaded_at DESC 
            LIMIT 1
        """)

        result = db.execute(query,  {"user_id": userId}).fetchone()

        if result:
            return {"hasCv": True, "extractedText": result[0]}
        else:
            return {"hasCv": False}

    except ProgrammingError as e:
        if "relation" in str(e) and "does not exist" in str(e):
            return {"hasCv": False}
        raise e

@router.get("/users/{userId}/essays")
def export_user_essays(
    userId: str,
    x_internal_api_key: str = Header(None),
    db: Session = Depends(get_db),
):
    expected_key = os.getenv("INTERNAL_API_KEY")
    if expected_key and x_internal_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid Internal API Key")

    essays = db.query(Essay).filter(Essay.user_id == userId).all()
    return {
        "essays": [
            {
                "id": essay.id,
                "s3Key": essay.s3_key,
                "essayText": essay.extracted_text,
                "uploadedAt": essay.uploaded_at.isoformat() if essay.uploaded_at else None,
                "status": essay.status,
                "submissionType": essay.submission_type,
                "examSessionId": essay.exam_session_id,
                "examType": essay.exam_type,
                "taskNumber": essay.task_number,
                "evaluationResult": essay.evaluation_result,
            }
            for essay in essays
        ]
    }


@router.post("/users/{userId}/purge")
def purge_deleted_account(
    userId: str,
    x_internal_api_key: str = Header(None),
    db: Session = Depends(get_db),
):
    expected_key = os.getenv("INTERNAL_API_KEY")
    if expected_key and x_internal_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid Internal API Key")
    return purge_user_data(db, userId)

