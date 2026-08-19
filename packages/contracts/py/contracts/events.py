from datetime import datetime
from typing import Literal, Dict, Union, Optional, List
from pydantic import BaseModel


class BaseEvent(BaseModel):
    type: str
    version: Literal['1.0'] = '1.0'
    timestamp: datetime
    correlationId: str

class UserUpdatedPayload(BaseModel):
    userId: str
    email: str
    subscriptionTier: Literal['free', 'paid']
    ects: float
    gpa: float
    gpaScale: Literal['4.0', '100']
    ieltsScore: float
    ieltsListening: Optional[float] = None
    ieltsReading: Optional[float] = None
    ieltsWriting: Optional[float] = None
    ieltsSpeaking: Optional[float] = None
    degreeLevel: str
    workExperienceYears: float
    extracurricularsScore: float
    targetCountries: List[str]
    fieldOfStudy: Optional[str] = None
    targetFieldOfStudy: Optional[str] = None


class UserUpdated(BaseEvent):
    type: Literal["user.updated"] = "user.updated"
    payload: UserUpdatedPayload

class CVUploadedPayload(BaseModel):
    userId: str
    s3Key: str
    fileName: str

class CVUploaded(BaseEvent):
    type: Literal["cv.uploaded"] = "cv.uploaded"
    payload: CVUploadedPayload


class CVProcessedPayload(BaseModel):
    userId: str
    extractedText: str
    status: Literal["success", "failed"]

class CVProcessed(BaseEvent):
    type: Literal["cv.processed"] = "cv.processed"
    payload: CVProcessedPayload

class ScholarshipMatchedPayload(BaseModel):
    userId: str
    programId: str
    score: float

class ScholarshipMatched(BaseEvent):
    type: Literal["scholarship.matched"] = "scholarship.matched"
    payload: ScholarshipMatchedPayload

class NotificationRequestedPayload(BaseModel):
    userId: str
    template: Literal["password_reset", "email_verify", "scholarship_alert"]
    recipientEmail: str
    templateData: Dict[str, Union[str, float, int]]

class NotificationRequested(BaseEvent):
    type: Literal["notification.requested"] = "notification.requested"
    payload: NotificationRequestedPayload

class IngestionCompletedPayload(BaseModel):
    sourceUrl: str
    chunksCreated: int

class IngestionCompleted(BaseEvent):
    type: Literal["ingestion.completed"] = "ingestion.completed"
    payload: IngestionCompletedPayload

# A Union type representing any valid domain event
DomainEvent = Union[
    UserUpdated,
    CVUploaded,
    CVProcessed,
    ScholarshipMatched,
    NotificationRequested,
    IngestionCompleted
]
