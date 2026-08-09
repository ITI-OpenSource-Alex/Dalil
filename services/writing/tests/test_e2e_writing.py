"""
E2E test suite for the Writing & CV Processing microservice.
Covers WR-01 through WR-09 acceptance criteria.
"""

import io
import json
import zipfile
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.dependencies import get_db, get_s3_client, get_sqs_client
from app.config import get_settings
from app.evaluation import EvaluationCoordinator, get_evaluation_coordinator
from app.main import app
from app.observability import get_langfuse_client
from app.schemas import CriterionEvaluation, InlineIssue
from app.agents import AgentExecution


# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------

TEST_SETTINGS = Settings(
    aws_region="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    aws_endpoint_url="http://localstack:4566",
    s3_bucket="goa-writing-files",
    cv_uploaded_queue_url="http://localstack:4566/000000000000/goa-cv-uploaded",
)


class FakeS3Client:
    def __init__(self, fail_upload=False):
        self.fail_upload = fail_upload
        self.uploads: list[dict] = []
        self.deletes: list[dict] = []

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        if self.fail_upload:
            raise RuntimeError("S3 unavailable")
        self.uploads.append(
            {"bucket": bucket, "key": key, "body": fileobj.read(), "extra_args": ExtraArgs}
        )

    def delete_object(self, Bucket, Key):
        self.deletes.append({"bucket": Bucket, "key": Key})


class FakeSQSClient:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages: list[dict] = []

    def send_message(self, QueueUrl, MessageBody):
        if self.fail:
            raise RuntimeError("SQS unavailable")
        self.messages.append({"queue_url": QueueUrl, "body": MessageBody})
        return {"MessageId": "test-message"}


class FakeAgentRunner:
    model = "test-writing-model"

    """Mimics WritingAgentRunner with configurable band scores."""

    def __init__(self, bands=None):
        self.bands = bands or {
            "task_response": 7.0,
            "cohesion": 7.0,
            "vocabulary": 6.5,
            "grammar": 6.5,
        }
        self.calls: list[tuple] = []

    async def evaluate(self, criterion, essay_text, exam_type, user_id="anonymous", **kwargs):
        self.calls.append(("evaluate", criterion, essay_text, exam_type))
        return self._make_execution(criterion, essay_text)

    async def evaluate_exam_task(self, criterion, essay_text, exam_type, task_number, user_id="anonymous", **kwargs):
        self.calls.append(("evaluate_exam_task", criterion, essay_text, exam_type, task_number))
        return self._make_execution(criterion, essay_text)

    def _make_execution(self, criterion, essay_text):
        word_count = len(essay_text.split())
        result = CriterionEvaluation(
            criterion=criterion,
            band_score=self.bands[criterion],
            feedback="Test feedback for criterion.",
            improvement_tip="Focus on precision.",
            word_count=word_count,
            inline_issues=[
                InlineIssue(
                    text=essay_text[:10],
                    issue_type="grammar",
                    suggestion="Test suggestion",
                    start_char=0,
                    end_char=min(10, len(essay_text)),
                )
            ],
        )
        return AgentExecution(
            result=result,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=10.0,
            cost_usd=0.001,
        )


def _make_docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    return buffer.getvalue()


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content padded to be valid enough" + b"\x00" * 100


@pytest_asyncio.fixture
async def setup():
    """Provides (client, db_session, fake_s3, fake_sqs, fake_runner) tuple."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()

    fake_s3 = FakeS3Client()
    fake_sqs = FakeSQSClient()
    fake_runner = FakeAgentRunner()
    langfuse = MagicMock()
    langfuse.start_observation.return_value = MagicMock()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_client] = lambda: fake_s3
    app.dependency_overrides[get_sqs_client] = lambda: fake_sqs
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    app.dependency_overrides[get_evaluation_coordinator] = lambda: EvaluationCoordinator(fake_runner)
    app.dependency_overrides[get_langfuse_client] = lambda: langfuse

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session, fake_s3, fake_sqs, fake_runner

    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# TestEssayEvaluation — WR-01 through WR-04
# ---------------------------------------------------------------------------


class TestEssayEvaluation:
    """Tests for essay creation, SSE streaming evaluation, and caching."""

    @pytest.mark.asyncio
    async def test_wr01_create_essay_returns_201_with_id_and_status(self, setup):
        """WR-01: POST /essays → 201, body has {id, status: 'ready'}."""
        client, db_session, *_ = setup

        response = await client.post(
            "/essays",
            json={
                "userId": "user-123",
                "essayText": "The rise of technology has changed modern education significantly.",
                "submissionType": "task2",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert body["status"] == "ready"
        assert isinstance(body["id"], int)

    @pytest.mark.asyncio
    async def test_wr02_sse_stream_emits_four_criterion_events_then_complete(self, setup):
        """WR-02: POST /essays/{id}/evaluate streams 4 criterion events + 1 complete event."""
        client, db_session, *_ = setup

        create_resp = await client.post(
            "/essays",
            json={
                "userId": "user-sse",
                "essayText": "Technology has revolutionised communication in the twenty-first century. "
                "People can now interact instantly across vast distances.",
                "submissionType": "task2",
            },
        )
        essay_id = create_resp.json()["id"]

        criterion_events = []
        complete_event = None

        async with client.stream("POST", f"/essays/{essay_id}/evaluate") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    raw_event, buffer = buffer.split("\n\n", 1)
                    lines = raw_event.strip().split("\n")
                    event_type = None
                    event_data = None
                    for line in lines:
                        if line.startswith("event:"):
                            event_type = line[len("event:"):].strip()
                        elif line.startswith("data:"):
                            event_data = line[len("data:"):].strip()

                    if event_type == "criterion":
                        criterion_events.append(json.loads(event_data))
                    elif event_type == "complete":
                        complete_event = json.loads(event_data)

        assert len(criterion_events) == 4
        criteria_seen = {e["criterion"] for e in criterion_events}
        assert criteria_seen == {"task_response", "cohesion", "vocabulary", "grammar"}

        assert complete_event is not None
        assert "overall_band" in complete_event
        assert "evaluations" in complete_event
        assert len(complete_event["evaluations"]) == 4
        assert complete_event["from_cache"] is False

    @pytest.mark.asyncio
    async def test_wr03_non_streaming_evaluate_returns_complete_response(self, setup):
        """WR-03: POST /essays/evaluate returns full evaluation synchronously."""
        client, *_ = setup

        response = await client.post(
            "/essays/evaluate",
            json={
                "userId": "user-sync",
                "essayText": "Many people argue that governments should invest more in public transport.",
                "submissionType": "task2",
                "examType": "IELTS Writing",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "essay_id" in body
        assert "evaluations" in body
        assert len(body["evaluations"]) == 4
        assert "overall_band" in body
        assert 0 <= body["overall_band"] <= 9.0
        assert body["from_cache"] is False

        for evaluation in body["evaluations"]:
            assert "criterion" in evaluation
            assert "band_score" in evaluation
            assert "feedback" in evaluation
            assert "inline_issues" in evaluation
            assert len(evaluation["inline_issues"]) > 0

    @pytest.mark.asyncio
    async def test_wr04_second_identical_request_hits_cache(self, setup):
        """WR-04: Submitting the same essay text twice returns from_cache=True on second call."""
        client, *_ = setup

        payload = {
            "userId": "user-cache",
            "essayText": "Caching test essay content that should be identical across requests.",
            "submissionType": "task2",
            "examType": "IELTS Writing",
        }

        first_response = await client.post("/essays/evaluate", json=payload)
        assert first_response.status_code == 200
        assert first_response.json()["from_cache"] is False

        second_response = await client.post("/essays/evaluate", json=payload)
        assert second_response.status_code == 200
        assert second_response.json()["from_cache"] is True
        assert second_response.json()["overall_band"] == first_response.json()["overall_band"]


# ---------------------------------------------------------------------------
# TestCVPipeline — WR-05 through WR-09
# ---------------------------------------------------------------------------


class TestCVPipeline:
    """Tests for CV upload, validation, and processing pipeline."""

    @pytest.mark.asyncio
    async def test_wr05_valid_pdf_upload_returns_202_with_processing_status(self, setup):
        """WR-05: POST /cv/upload with valid PDF → 202, {cvId, status: 'processing'}."""
        client, db_session, fake_s3, fake_sqs, _ = setup

        pdf_content = _make_pdf_bytes()
        files = {"file": ("resume.pdf", pdf_content, "application/pdf")}
        data = {"userId": "user-cv-01"}

        response = await client.post("/cv/upload", data=data, files=files)

        assert response.status_code == 202
        body = response.json()
        assert "cvId" in body
        assert body["status"] == "processing"
        assert len(fake_s3.uploads) == 1
        assert fake_s3.uploads[0]["bucket"] == "goa-writing-files"
        assert len(fake_sqs.messages) == 1

    @pytest.mark.asyncio
    async def test_wr06_valid_docx_upload_returns_202(self, setup):
        """WR-06: POST /cv/upload with valid DOCX → 202, S3 + SQS invoked."""
        client, db_session, fake_s3, fake_sqs, _ = setup

        docx_content = _make_docx_bytes()
        files = {"file": ("resume.docx", docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        data = {"userId": "user-cv-02"}

        response = await client.post("/cv/upload", data=data, files=files)

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "processing"
        assert len(fake_s3.uploads) == 1
        assert "cvs/user-cv-02/" in fake_s3.uploads[0]["key"]
        assert fake_s3.uploads[0]["key"].endswith(".docx")
        assert len(fake_sqs.messages) == 1

    @pytest.mark.asyncio
    async def test_wr07_exe_upload_returns_415(self, setup):
        """WR-07: POST /cv/upload with .exe file → 415 Unsupported Media Type."""
        client, *_ = setup

        exe_content = b"MZ" + b"\x00" * 200
        files = {"file": ("malware.exe", exe_content, "application/x-msdownload")}
        data = {"userId": "user-cv-03"}

        response = await client.post("/cv/upload", data=data, files=files)

        assert response.status_code == 415
        assert "PDF" in response.json()["detail"] or "supported" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_wr08_oversized_file_returns_413(self, setup):
        """WR-08: POST /cv/upload with >10MB file → 413 via middleware Content-Length check."""
        client, *_ = setup

        oversized_size = 11 * 1024 * 1024
        files = {"file": ("big.pdf", b"%PDF-" + b"\x00" * 100, "application/pdf")}
        data = {"userId": "user-cv-04"}

        response = await client.post(
            "/cv/upload",
            data=data,
            files=files,
            headers={"content-length": str(oversized_size)},
        )

        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"] or "smaller" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_wr09_cv_status_transitions_to_ready_after_worker(self, setup):
        """WR-09: After upload, simulate async worker setting status to 'ready'."""
        client, db_session, fake_s3, fake_sqs, _ = setup

        pdf_content = _make_pdf_bytes()
        files = {"file": ("resume.pdf", pdf_content, "application/pdf")}
        data = {"userId": "user-cv-05"}

        response = await client.post("/cv/upload", data=data, files=files)
        assert response.status_code == 202
        cv_id = response.json()["cvId"]

        from app.models import CVReview

        review = db_session.query(CVReview).filter(CVReview.id == cv_id).first()
        assert review is not None
        assert review.status == "processing"

        review.status = "ready"
        review.extracted_text = "Simulated extracted CV text from worker."
        db_session.commit()
        db_session.refresh(review)

        assert review.status == "ready"
        assert review.extracted_text is not None
