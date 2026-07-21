# Event Catalog

This document catalogues all event types exchanged asynchronously between microservices using the SQS event queues.

---

## Base Event Envelope

Every event conforms to a shared base structure containing metadata for schema validation and distributed tracing correlation.

### Python / Pydantic Base Schema
```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel

class BaseEvent(BaseModel):
    type: str
    version: Literal['1.0'] = '1.0'
    timestamp: datetime
    correlationId: str
```

---

## Active Event Types

### 1. `user.updated`
* **Publisher**: `User Service`
* **Subscribers / Consumers**: `Orchestration Service`
* **Description**: Dispatched when a user modifies their account settings or updates their subscription plan.
* **Payload Structure**:
```json
{
  "userId": "usr_abc123",
  "email": "user@example.com",
  "subscribtionTier": "free" // "free" or "paid"
}
```

### 2. `cv.uploaded`
* **Publisher**: `Gateway Service`
* **Subscribers / Consumers**: `Ingestion Worker`
* **Description**: Fired when a user successfully uploads their CV document to the S3 bucket.
* **Payload Structure**:
```json
{
  "userId": "usr_abc123",
  "s3Key": "cvs/usr_abc123_resume.pdf",
  "fileName": "my_resume.pdf"
}
```

### 3. `CVProcessed`
* **Publisher**: `CV Processor`
* **Subscribers / Consumers**: onboarding, orchestration, and interested domain consumers
* **Description**: Fired when CV text and structured-field extraction finishes. Extracted content remains in `writing_db`; the event identifies the durable record.
* **Event fields in addition to the base envelope**:
```json
{
  "userId": "usr_abc123",
  "cvId": 42,
  "s3Key": "cvs/usr_abc123/resume.pdf",
  "status": "ready"
}
```

### 4. `scholarship.matched`
* **Publisher**: `RAG Service` / `Matching Engine`
* **Subscribers / Consumers**: `Notification Service`
* **Description**: Emitted when a new scholarship matches a user profile with a confidence score above the alert threshold.
* **Payload Structure**:
```json
{
  "userId": "usr_abc123",
  "programId": "sch_999",
  "score": 0.88
}
```

### 5. `notification.requested`
* **Publisher**: Any service (e.g. User Service, Orchestration)
* **Subscribers / Consumers**: `Notification Service`
* **Description**: Triggered when a service requests an email message to be sent to a user.
* **Payload Structure**:
```json
{
  "userId": "usr_abc123",
  "template": "password_reset", // "password_reset", "email_verify", or "scholarship_alert"
  "recipientEmail": "user@example.com",
  "templateData": {
    "reset_url": "https://goa.edu/reset?token=xyz"
  }
}
```

### 6. `ingestion.completed`
* **Publisher**: `Ingestion Worker`
* **Subscribers / Consumers**: `RAG Service`
* **Description**: Emitted when a document source (e.g. scholarship requirement webpage) has been parsed, chunked, embedded, and stored in RAG.
* **Payload Structure**:
```json
{
  "sourceUrl": "https://daad.de/scholarships/study-grants",
  "chunksCreated": 14
}
```
