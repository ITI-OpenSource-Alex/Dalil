import hashlib
import io
import json
from types import SimpleNamespace

import pytest
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import MAX_CV_SIZE_BYTES, Settings
from app.database import Base
from app.models import CVReview
from cv_processor.extraction import extract_plain_text
from cv_processor.handler import (
    CVProcessor,
    CVProcessorConfigurationError,
    get_processor,
    lambda_handler,
)
from cv_processor.structured import (
    StructuredCV,
    StructuredCVExtractor,
    StructuredExecution,
)
from tests.conftest import FakeSQSClient
from tests.cv_fixtures import minimal_pdf_bytes


def _docx_bytes() -> bytes:
    document = Document()
    document.add_heading("Jane Doe", level=1)
    document.add_paragraph("Python Engineer")
    document.add_paragraph("jane@example.com")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class FakeS3Client:
    def __init__(self, objects):
        self.objects = objects
        self.head_calls = []
        self.get_calls = []

    def head_object(self, Bucket, Key):
        self.head_calls.append((Bucket, Key))
        item = self.objects[Key]
        return {
            "ContentLength": item.get("content_length", len(item.get("body", b""))),
            "ContentType": item.get("content_type"),
            "Metadata": item.get("metadata", {}),
        }

    def get_object(self, Bucket, Key):
        self.get_calls.append((Bucket, Key))
        return {"Body": io.BytesIO(self.objects[Key]["body"])}


class FakeStructuredExtractor:
    model = "claude-haiku-4-5-20251001"

    def __init__(self):
        self.calls = []

    def extract(self, text):
        self.calls.append(text)
        return StructuredExecution(
            data=StructuredCV(
                name="Jane Doe",
                email="jane@example.com",
                phone="+1 555 0100",
                degree="BSc",
                institution="Example University",
                graduation_year="2024",
                field_of_study="Computer Science",
                skills=["Python", "SQL"],
                work_experience=[
                    {"title": "Engineer", "org": "Example Inc", "years": "2"}
                ],
                languages=["English"],
            ),
            input_tokens=100,
            output_tokens=50,
            latency_ms=25,
            cost_usd=0.00035,
        )


@pytest.fixture
def processor_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def processor_settings():
    return Settings(
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_endpoint_url="http://localstack:4566",
        s3_bucket="goa-writing-files",
        cv_uploaded_queue_url="uploaded-queue",
        cv_processed_queue_url="processed-queue",
    )


def _event(key: str) -> dict:
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "responseElements": {"x-amz-request-id": "request-123"},
                "s3": {
                    "bucket": {"name": "goa-writing-files"},
                    "object": {"key": key},
                },
            }
        ]
    }


def _processor(objects, processor_db, processor_settings):
    extractor = FakeStructuredExtractor()
    sqs = FakeSQSClient()
    processor = CVProcessor(
        s3_client=FakeS3Client(objects),
        sqs_client=sqs,
        session_factory=processor_db,
        structured_extractor=extractor,
        settings=processor_settings,
    )
    return processor, processor.s3, sqs, extractor


def test_pdfplumber_extracts_plain_text_from_pdf_fixture():
    text = extract_plain_text(minimal_pdf_bytes("Jane Doe Python Engineer"), "pdf")

    assert "Jane Doe" in text
    assert "Python Engineer" in text


def test_python_docx_extracts_plain_text_from_docx_fixture():
    text = extract_plain_text(_docx_bytes(), "docx")

    assert "Jane Doe" in text
    assert "jane@example.com" in text


def test_structured_extraction_returns_every_expected_field():
    payload = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+1 555 0100",
        "degree": "BSc",
        "institution": "Example University",
        "graduation_year": "2024",
        "field_of_study": "Computer Science",
        "skills": ["Python"],
        "work_experience": [
            {"title": "Engineer", "org": "Example Inc", "years": "2"}
        ],
        "languages": ["English"],
    }
    response = SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps(payload))],
        usage=SimpleNamespace(input_tokens=120, output_tokens=80),
    )
    messages = SimpleNamespace(create=lambda **kwargs: response)
    extractor = StructuredCVExtractor(SimpleNamespace(messages=messages))

    execution = extractor.extract("Jane Doe CV")

    assert set(execution.data.model_dump()) == set(payload)
    assert execution.data.work_experience[0].org == "Example Inc"
    assert execution.input_tokens == 120
    assert execution.output_tokens == 80


def test_structured_extraction_retries_one_invalid_json_response():
    valid = {
        "name": "Jane Doe",
        "email": None,
        "phone": None,
        "degree": None,
        "institution": None,
        "graduation_year": None,
        "field_of_study": None,
        "skills": [],
        "work_experience": [],
        "languages": [],
    }
    responses = iter(
        [
            SimpleNamespace(
                content=[SimpleNamespace(text="not json")],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            ),
            SimpleNamespace(
                content=[SimpleNamespace(text=json.dumps(valid))],
                usage=SimpleNamespace(input_tokens=20, output_tokens=10),
            ),
        ]
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return next(responses)

    extractor = StructuredCVExtractor(
        SimpleNamespace(messages=SimpleNamespace(create=create))
    )

    execution = extractor.extract("Jane Doe CV")

    assert execution.data.name == "Jane Doe"
    assert len(calls) == 2
    assert "previous response" in calls[1]["messages"][0]["content"]


def test_success_persists_text_structured_data_and_publishes_event(
    processor_db, processor_settings
):
    key = "cvs/user-123/resume.pdf"
    body = minimal_pdf_bytes("Jane Doe Python Engineer")
    content_hash = hashlib.sha256(body).hexdigest()
    processor, s3, sqs, extractor = _processor(
        {
            key: {
                "body": body,
                "content_type": "application/pdf",
                "metadata": {"sha256": content_hash},
            }
        },
        processor_db,
        processor_settings,
    )

    result = processor.process_record(_event(key)["Records"][0])

    assert result["status"] == "ready"
    assert result["outcome"] == "success"
    assert len(extractor.calls) == 1
    assert len(s3.get_calls) == 1
    with processor_db() as db:
        review = db.query(CVReview).one()
        assert review.extracted_text == "Jane Doe Python Engineer"
        assert review.structured_data["skills"] == ["Python", "SQL"]
        assert review.content_hash == content_hash
        assert review.error_message is None
        assert review.processed_at is not None

    event = json.loads(sqs.messages[0]["body"])
    assert event["type"] == "CVProcessed"
    assert event["userId"] == "user-123"
    assert event["cvId"] == result["cvId"]
    assert event["s3Key"] == key
    assert event["status"] == "ready"


def test_unsupported_type_is_failed_without_download_or_exception(
    processor_db, processor_settings
):
    key = "cvs/user-123/resume.exe"
    processor, s3, sqs, extractor = _processor(
        {key: {"body": b"MZ", "content_type": "application/octet-stream"}},
        processor_db,
        processor_settings,
    )

    result = processor.process_record(_event(key)["Records"][0])

    assert result["status"] == "failed"
    assert s3.get_calls == []
    assert extractor.calls == []
    with processor_db() as db:
        assert "Only PDF and DOCX" in db.query(CVReview).one().error_message
    assert json.loads(sqs.messages[0]["body"])["status"] == "failed"


def test_oversized_file_is_rejected_from_head_before_download(
    processor_db, processor_settings
):
    key = "cvs/user-123/resume.pdf"
    processor, s3, sqs, extractor = _processor(
        {
            key: {
                "content_length": MAX_CV_SIZE_BYTES + 1,
                "content_type": "application/pdf",
            }
        },
        processor_db,
        processor_settings,
    )

    result = processor.process_record(_event(key)["Records"][0])

    assert result["status"] == "failed"
    assert s3.get_calls == []
    assert extractor.calls == []
    assert len(sqs.messages) == 1


def test_duplicate_ready_object_skips_second_download_and_llm_call(
    processor_db, processor_settings
):
    key = "cvs/user-123/resume.pdf"
    body = minimal_pdf_bytes("Jane Doe Python Engineer")
    content_hash = hashlib.sha256(body).hexdigest()
    processor, s3, sqs, extractor = _processor(
        {
            key: {
                "body": body,
                "content_type": "application/pdf",
                "metadata": {"sha256": content_hash},
            }
        },
        processor_db,
        processor_settings,
    )

    first = processor.process_record(_event(key)["Records"][0])
    second = processor.process_record(_event(key)["Records"][0])

    assert first["outcome"] == "success"
    assert second["outcome"] == "skipped"
    assert len(s3.get_calls) == 1
    assert len(extractor.calls) == 1
    assert len(sqs.messages) == 2
    assert json.loads(sqs.messages[1]["body"])["status"] == "ready"


def test_lambda_handler_accepts_sqs_wrapped_s3_notification(monkeypatch):
    calls = []
    fake_processor = SimpleNamespace(process_record=lambda record: calls.append(record) or {})
    monkeypatch.setattr("cv_processor.handler.get_processor", lambda: fake_processor)
    event = {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "body": json.dumps(_event("cvs/user-123/resume.pdf")),
            }
        ]
    }

    response = lambda_handler(event, None)

    assert response["processed"] == 1
    assert calls[0]["s3"]["object"]["key"] == "cvs/user-123/resume.pdf"


def test_default_processor_fails_fast_without_anthropic_key(
    monkeypatch, processor_settings
):
    monkeypatch.setattr("cv_processor.handler.get_settings", lambda: processor_settings)
    get_processor.cache_clear()
    try:
        with pytest.raises(CVProcessorConfigurationError, match="ANTHROPIC_API_KEY"):
            get_processor()
    finally:
        get_processor.cache_clear()
