from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class Essay(Base):
    __tablename__ = "essays"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, nullable=False)

    s3_key = Column(String, nullable=True)

    extracted_text = Column(Text, nullable=False)

    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    status = Column(String, default="pending")

    submission_type = Column(String)
    exam_session_id = Column(String, nullable=True)
    exam_type = Column(String, nullable=True)
    task_number = Column(Integer, nullable=True)
    evaluation_cache_key = Column(String(64), nullable=True, index=True)
    evaluation_result = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)


class CVReview(Base):
    __tablename__ = "cv_reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    s3_key = Column(String(512), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="processing")
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
