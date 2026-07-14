# GOA Exam Service

## Overview

This service powers the exam question bank for GOA. For this task, the work was focused on extending the existing Exam service with Cambridge IELTS content ingestion while reusing the current question table and repository architecture.

## What was implemented in this task

### Ingestion support

The Exam service now includes an ingestion module under app/ingestion for handling Cambridge IELTS content.

Supported capabilities:

- parse_text() for unit-test style text input
- parse_pdf() for PDF input using pdfplumber
- reading and listening parsing flow
- directory-based ingestion for folders containing Cambridge IELTS book content
- idempotent loading using the existing questions repository

### Internal question-bank stats

A new internal endpoint was added:

- GET /internal/question-bank/stats

It returns counts grouped by exam type and skill area.

### Notes on scope

The implementation intentionally avoids schema redesign and keeps all database logic inside the existing repository layer.

TODOs that remain for future tickets:

- Writing and Speaking ingestion are not fully implemented yet because the current schema and downstream content format are not sufficient for full coverage.
- Actual S3 audio upload is still deferred; the listening flow stores the expected S3 key pattern only.

---

## Project structure

Key folders:

- app/api - FastAPI routers
- app/core - configuration, database, security
- app/models - domain models
- app/repositories - database access layer
- app/schemas - request/response schemas
- app/services - business logic
- app/ingestion - new ingestion pipeline
- tests - unit and integration tests

---

## Requirements

The service uses:

- Python 3.11+
- FastAPI
- PostgreSQL
- asyncpg
- pdfplumber

Install dependencies:

```powershell
cd .\services\exam
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Environment setup

The service expects environment variables such as:

```powershell
$env:DATABASE_URL = "postgresql://goa:goa@localhost:5432/exam_test"
$env:INTERNAL_API_KEY = "test-internal-key"
```

Make sure PostgreSQL is running and the database exists.

---

## Run the service locally

From the Exam service folder:

```powershell
cd .\services\exam
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8085
```

Then open:

- http://localhost:8085/health

---

## Run ingestion

The ingestion logic is available through the ingestion module and repository layer.

Example usage from Python:

```python
from app.repositories.question_repository import QuestionRepository
from app.ingestion.ingest import IngestionService
from app.core.database import db

# connect to DB first if needed
# await db.connect()

repository = QuestionRepository(db.pool)
service = IngestionService(repository)

# parse a text payload
result = await service.ingest("Book Ref: IELTS-17\nTest Number: 1\nExam Type: academic\nSkill Area: reading\nQuestion 1. Choose the correct answer.\n", skill_area="reading")
print(result)
```

Directory ingestion example:

```python
from app.repositories.question_repository import QuestionRepository
from app.ingestion.loader import QuestionLoader
from app.core.database import db

repository = QuestionRepository(db.pool)
loader = QuestionLoader(repository)
await loader.ingest_directory("./sample_books")
```

---

## Internal endpoint

### Stats endpoint

```powershell
curl -H "X-Internal-API-Key: test-internal-key" http://localhost:8085/internal/question-bank/stats
```

Example response:

```json
{
  "academic": {
    "reading": 20,
    "listening": 20
  },
  "general": {
    "reading": 20,
    "listening": 20
  }
}
```

---

## Running tests

Run all tests:

```powershell
cd .\services\exam
.\.venv\Scripts\python.exe -m pytest
```

Run lint:

```powershell
cd .\services\exam
.\.venv\Scripts\python.exe -m ruff check app tests
```

---

## Notes

This task was implemented incrementally and stays within the current architecture:

- no new tables were introduced
- the existing questions table is reused
- session, grading, timer, and exam workflow were left unchanged

## PDF extraction and OCR fallback

- The ingestion pipeline first uses `pdfplumber` to extract searchable PDF text.
- If `pdfplumber` returns empty text (common with scanned image PDFs), the parser automatically falls back to OCR.
- OCR fallback uses `pdf2image` + `pytesseract` + `Pillow`, then continues through the same existing reading/listening parsers.
- OCR is only used as a fallback; it does not replace the `pdfplumber` extraction path.

### Windows OCR setup

1. Install Tesseract OCR:
   - [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
2. Install Poppler for Windows (required by `pdf2image`):
   - [https://github.com/oschwartz10612/poppler-windows/releases](https://github.com/oschwartz10612/poppler-windows/releases)
3. Add both binaries to your `PATH`:
   - Tesseract install folder (contains `tesseract.exe`)
   - Poppler `bin` folder (contains `pdftoppm.exe`)
4. Verify installation:

```powershell
tesseract --version
```

If OCR dependencies are missing, ingestion raises a descriptive runtime error instead of silently skipping extraction.

### Docker OCR (self-contained)

- OCR works entirely inside the Exam Docker image.
- Native OCR dependencies (`tesseract-ocr`, `poppler-utils`) are installed automatically during `docker compose build exam`.
- No manual Windows installation of Tesseract or Poppler is required when running Exam through Docker.
