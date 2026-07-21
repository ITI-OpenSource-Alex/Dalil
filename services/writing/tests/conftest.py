import io
import os
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


SERVICE_ROOT = Path(__file__).resolve().parents[1]
try:
    REPOSITORY_ROOT = SERVICE_ROOT.parents[1]
except IndexError:
    REPOSITORY_ROOT = Path("/")
CONTRACTS_ROOT = REPOSITORY_ROOT / "packages" / "contracts" / "py"
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(CONTRACTS_ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.config import Settings, get_settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.dependencies import get_db, get_s3_client, get_sqs_client  # noqa: E402
from app.main import app  # noqa: E402
from app.agents import AgentExecution  # noqa: E402
from app.evaluation import EvaluationCoordinator, get_evaluation_coordinator  # noqa: E402
from app.metrics import cache_hit_tracker  # noqa: E402
from app.observability import get_langfuse_client  # noqa: E402
from app.schemas import CriterionEvaluation, InlineIssue  # noqa: E402


class FakeS3Client:
    def __init__(self, fail_upload=False):
        self.fail_upload = fail_upload
        self.uploads = []
        self.deletes = []

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        if self.fail_upload:
            raise RuntimeError("S3 unavailable")
        self.uploads.append(
            {
                "bucket": bucket,
                "key": key,
                "body": fileobj.read(),
                "extra_args": ExtraArgs,
            }
        )

    def delete_object(self, Bucket, Key):
        self.deletes.append({"bucket": Bucket, "key": Key})


class FakeSQSClient:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def send_message(self, QueueUrl, MessageBody):
        if self.fail:
            raise RuntimeError("SQS unavailable")
        self.messages.append({"queue_url": QueueUrl, "body": MessageBody})
        return {"MessageId": "test-message"}


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def fake_s3():
    return FakeS3Client()


@pytest.fixture
def fake_sqs():
    return FakeSQSClient()


@pytest.fixture
def client(db_session, fake_s3, fake_sqs):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_client] = lambda: fake_s3
    app.dependency_overrides[get_sqs_client] = lambda: fake_sqs
    app.dependency_overrides[get_settings] = lambda: Settings(
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_endpoint_url="http://localstack:4566",
        s3_bucket="goa-writing-files",
        cv_uploaded_queue_url="http://localstack:4566/000000000000/goa-cv-uploaded",
    )
    cache_hit_tracker.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def docx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    return buffer.getvalue()


class FakeWritingAgentRunner:
    def __init__(self, delays=None, bands=None):
        self.delays = delays or {}
        self.bands = bands or {
            "task_response": 6.5,
            "cohesion": 7.0,
            "vocabulary": 6.0,
            "grammar": 6.5,
        }
        self.calls = []

    async def evaluate(self, criterion, essay_text, exam_type):
        import asyncio

        self.calls.append((criterion, essay_text, exam_type))
        await asyncio.sleep(self.delays.get(criterion, 0))
        issue_text = essay_text[: min(12, len(essay_text))]
        word_count = len(essay_text.split())
        result = CriterionEvaluation(
            criterion=criterion,
            band_score=self.bands[criterion],
            feedback=(
                "Focused criterion feedback.\n\nSentence-level examples:\n"
                "1. First exact example.\n2. Second exact example.\n"
                "3. Third exact example."
            ),
            improvement_tip="Focus on precision and coherence.",
            word_count=word_count,
            inline_issues=[
                InlineIssue(
                    text=issue_text,
                    issue_type="grammar",
                    suggestion="Specific test revision",
                    start_char=0,
                    end_char=len(issue_text),
                )
            ],
        )
        return AgentExecution(
            result=result,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=self.delays.get(criterion, 0) * 1000,
            cost_usd=0.001,
        )


@pytest.fixture
def fake_agent_runner():
    return FakeWritingAgentRunner()


@pytest.fixture
def evaluation_client(client, fake_agent_runner):
    from unittest.mock import MagicMock

    langfuse = MagicMock()
    trace = MagicMock()
    langfuse.trace.return_value = trace
    app.dependency_overrides[get_evaluation_coordinator] = lambda: EvaluationCoordinator(
        fake_agent_runner
    )
    app.dependency_overrides[get_langfuse_client] = lambda: langfuse
    yield client, fake_agent_runner, langfuse, trace
