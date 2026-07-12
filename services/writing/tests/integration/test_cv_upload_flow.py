import json
import os
import time
from uuid import uuid4

import boto3
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import CVReview


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def integration_clients():
    if os.getenv("RUN_WRITING_INTEGRATION") != "1":
        pytest.skip("Set RUN_WRITING_INTEGRATION=1 with PostgreSQL and LocalStack running")

    get_settings.cache_clear()
    settings = get_settings()
    kwargs = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "endpoint_url": settings.aws_endpoint_url,
    }
    yield TestClient(app), boto3.client("s3", **kwargs), boto3.client("sqs", **kwargs)


def test_pdf_upload_persists_object_row_event_and_s3_trigger(integration_clients):
    client, s3, sqs = integration_clients
    settings = get_settings()
    processor_queue_url = sqs.get_queue_url(QueueName="goa-cv-processing")["QueueUrl"]
    sqs.purge_queue(QueueUrl=settings.cv_uploaded_queue_url)
    sqs.purge_queue(QueueUrl=processor_queue_url)
    user_id = f"integration-{uuid4().hex}"

    response = client.post(
        "/cv/upload",
        data={"userId": user_id},
        files={"file": ("resume.pdf", b"%PDF-1.7\nintegration\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 202
    cv_id = response.json()["cvId"]
    with SessionLocal() as db:
        review = db.get(CVReview, cv_id)
        assert review is not None
        assert review.status == "processing"
        assert review.original_filename == "resume.pdf"
        s3_key = review.s3_key

    assert s3.head_object(Bucket=settings.s3_bucket, Key=s3_key)["ContentLength"] > 0

    domain_messages = sqs.receive_message(
        QueueUrl=settings.cv_uploaded_queue_url,
        WaitTimeSeconds=5,
        MaxNumberOfMessages=10,
    ).get("Messages", [])
    assert any(
        json.loads(message["Body"])["payload"]["s3Key"] == s3_key
        for message in domain_messages
    )

    processor_messages = sqs.receive_message(
        QueueUrl=processor_queue_url,
        WaitTimeSeconds=5,
        MaxNumberOfMessages=10,
    ).get("Messages", [])
    assert any(s3_key in message["Body"] for message in processor_messages)

    if os.getenv("RUN_CV_PROCESSOR_E2E") == "1":
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with SessionLocal() as db:
                if db.get(CVReview, cv_id).status == "ready":
                    break
            time.sleep(0.5)
        else:
            pytest.fail("GOA-087 did not transition the CV review to ready")

    s3.delete_object(Bucket=settings.s3_bucket, Key=s3_key)
    with SessionLocal() as db:
        db.query(CVReview).filter(CVReview.id == cv_id).delete()
        db.commit()
