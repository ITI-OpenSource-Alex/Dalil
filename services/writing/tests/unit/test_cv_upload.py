import json

import pytest

from app.config import MAX_CV_REQUEST_BYTES, MAX_CV_SIZE_BYTES
from app.dependencies import get_db, get_s3_client, get_sqs_client
from app.main import app
from app.models import CVReview
from tests.conftest import FakeS3Client, FakeSQSClient


PDF = b"%PDF-1.7\nminimal test PDF\n%%EOF"
DOC = bytes.fromhex("D0CF11E0A1B11AE1") + b"test document"


def upload(client, filename, body, content_type, headers=None):
    return client.post(
        "/cv/upload",
        data={"userId": "user-123"},
        files={"file": (filename, body, content_type)},
        headers=headers or {},
    )


def test_content_length_over_limit_returns_413_before_s3(client, fake_s3):
    response = upload(
        client,
        "resume.pdf",
        PDF,
        "application/pdf",
        headers={"content-length": str(MAX_CV_REQUEST_BYTES + 1)},
    )

    assert response.status_code == 413
    assert fake_s3.uploads == []


def test_file_exactly_at_limit_is_accepted(client, fake_s3):
    body = b"%PDF-" + (b"a" * (MAX_CV_SIZE_BYTES - 5))

    response = upload(client, "resume.pdf", body, "application/pdf")

    assert response.status_code == 202
    assert len(fake_s3.uploads[0]["body"]) == MAX_CV_SIZE_BYTES


def test_streamed_file_over_limit_returns_413_before_s3(client, fake_s3):
    response = upload(
        client,
        "resume.pdf",
        b"%PDF-" + (b"a" * MAX_CV_SIZE_BYTES),
        "application/pdf",
        headers={"content-length": "1"},
    )

    assert response.status_code == 413
    assert fake_s3.uploads == []


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("malware.exe", "application/octet-stream"),
        ("avatar.png", "image/png"),
    ],
)
def test_unsupported_files_return_415(client, fake_s3, filename, content_type):
    response = upload(client, filename, b"unsupported", content_type)

    assert response.status_code == 415
    assert fake_s3.uploads == []


def test_spoofed_pdf_is_rejected(client, fake_s3):
    response = upload(client, "malware.pdf", b"MZ executable", "application/pdf")

    assert response.status_code == 415
    assert fake_s3.uploads == []


def test_mismatched_extension_is_rejected(client, fake_s3):
    response = upload(client, "resume.exe", PDF, "application/pdf")

    assert response.status_code == 415
    assert fake_s3.uploads == []


def test_unsafe_user_id_is_rejected(client, fake_s3):
    response = client.post(
        "/cv/upload",
        data={"userId": "../../another-user"},
        files={"file": ("resume.pdf", PDF, "application/pdf")},
    )

    assert response.status_code == 422
    assert fake_s3.uploads == []


@pytest.mark.parametrize(
    ("filename", "body", "content_type", "extension"),
    [
        ("resume.pdf", PDF, "application/pdf", ".pdf"),
        ("resume.doc", DOC, "application/msword", ".doc"),
    ],
)
def test_pdf_and_doc_are_accepted(
    client, fake_s3, filename, body, content_type, extension
):
    response = upload(client, filename, body, content_type)

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert len(fake_s3.uploads) == 1
    assert fake_s3.uploads[0]["key"].startswith("cvs/user-123/")
    assert fake_s3.uploads[0]["key"].endswith(extension)
    assert fake_s3.uploads[0]["body"] == body


def test_docx_is_accepted(client, fake_s3, docx_bytes):
    response = upload(
        client,
        "resume.docx",
        docx_bytes,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert response.status_code == 202
    assert fake_s3.uploads[0]["key"].endswith(".docx")


def test_success_creates_row_and_publishes_contract(
    client, db_session, fake_s3, fake_sqs
):
    response = upload(
        client,
        "../private/resume.pdf",
        PDF,
        "application/pdf",
        headers={"x-correlation-id": "correlation-123"},
    )

    assert response.status_code == 202
    review = db_session.query(CVReview).one()
    assert response.json() == {"cvId": review.id, "status": "processing"}
    assert review.user_id == "user-123"
    assert review.original_filename == "resume.pdf"
    assert review.s3_key == fake_s3.uploads[0]["key"]

    assert len(fake_sqs.messages) == 1
    event = json.loads(fake_sqs.messages[0]["body"])
    assert event["type"] == "cv.uploaded"
    assert event["version"] == "1.0"
    assert event["correlationId"] == "correlation-123"
    assert event["payload"] == {
        "userId": "user-123",
        "s3Key": review.s3_key,
        "fileName": "resume.pdf",
    }


def test_database_failure_does_not_write_s3(client, fake_s3):
    class FailingSession:
        def add(self, _review):
            raise RuntimeError("database unavailable")

        def rollback(self):
            pass

    def override_db():
        yield FailingSession()

    app.dependency_overrides[get_db] = override_db

    response = upload(client, "resume.pdf", PDF, "application/pdf")

    assert response.status_code == 503
    assert fake_s3.uploads == []


def test_s3_failure_removes_database_row(client, db_session, fake_sqs):
    failing_s3 = FakeS3Client(fail_upload=True)
    app.dependency_overrides[get_s3_client] = lambda: failing_s3

    response = upload(client, "resume.pdf", PDF, "application/pdf")

    assert response.status_code == 502
    assert db_session.query(CVReview).count() == 0
    assert fake_sqs.messages == []


def test_sqs_failure_removes_object_and_database_row(client, db_session, fake_s3):
    app.dependency_overrides[get_sqs_client] = lambda: FakeSQSClient(fail=True)

    response = upload(client, "resume.pdf", PDF, "application/pdf")

    assert response.status_code == 502
    assert db_session.query(CVReview).count() == 0
    assert len(fake_s3.uploads) == 1
    assert fake_s3.deletes == [
        {"bucket": "goa-writing-files", "key": fake_s3.uploads[0]["key"]}
    ]


def test_openapi_documents_multipart_and_responses(client):
    operation = client.get("/openapi.json").json()["paths"]["/cv/upload"]["post"]

    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert {"202", "413", "415"}.issubset(operation["responses"])
