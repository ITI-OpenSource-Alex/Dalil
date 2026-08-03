from datetime import datetime
from typing import Literal, Dict, Union
from pydantic import BaseModel


class BaseEvent(BaseModel):
    type: str
    version: Literal['1.0'] = '1.0'
    timestamp: datetime
    correlationId: str

class UserUpdatedPayload(BaseModel):
    userId: str
    email: str
    subscribtionTier: Literal['free', 'paid']


class UserUpdated(BaseEvent):
    type: Literal["user.updated"] = "user.updated"
    payload: UserUpdatedPayload

class AccountDeletedPayload(BaseModel):
    userId: str
    deletedAt: datetime

class AccountDeleted(BaseEvent):
    type: Literal["account.deleted"] = "account.deleted"
    payload: AccountDeletedPayload
class CVUploadedPayload(BaseModel):
    userId: str
    s3Key: str
    fileName: str

class CVUploaded(BaseEvent):
    type: Literal["cv.uploaded"] = "cv.uploaded"
    payload: CVUploadedPayload


class CVProcessed(BaseEvent):
    type: Literal["CVProcessed"] = "CVProcessed"
    userId: str
    cvId: int
    s3Key: str
    status: Literal["ready", "failed"]

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

class ScholarshipMatchedNotification(BaseModel):
    eventType: Literal["ScholarshipMatched"] = "ScholarshipMatched"
    userId: str
    programId: str
    programName: str | None = None
    provider: str | None = None
    country: str | None = None
    deadline: str | None = None
    score: float
    cycleDate: str


class DeadlineReminderNotification(BaseModel):
    eventType: Literal["DEADLINE_REMINDER"] = "DEADLINE_REMINDER"
    userId: str
    programId: str
    programName: str | None = None
    provider: str | None = None
    country: str | None = None
    deadline: str | None = None
    score: float
    cycleDate: str


# A Union type representing any valid domain event
DomainEvent = Union[
    UserUpdated,
    AccountDeleted,
    CVUploaded,
    CVProcessed,
    ScholarshipMatched,
    NotificationRequested,
    IngestionCompleted
]


