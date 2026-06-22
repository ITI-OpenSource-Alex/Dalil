from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import DateTime
from sqlalchemy import Integer
from datetime import datetime

from app.database import Base


class Essay(Base):
    __tablename__ = "essays"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, nullable=False)

    s3_key = Column(String, nullable=True)

    extracted_text = Column(Text, nullable=False)

    uploaded_at = Column(DateTime, default=datetime.utcnow)

    status = Column(String, default="pending")

    submission_type = Column(String)
    exam_session_id = Column(String, nullable=True)