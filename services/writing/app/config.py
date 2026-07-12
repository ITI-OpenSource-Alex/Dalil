import os
from dataclasses import dataclass
from functools import lru_cache


MAX_CV_SIZE_BYTES = 10 * 1024 * 1024
MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_CV_REQUEST_BYTES = MAX_CV_SIZE_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
READ_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Settings:
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_endpoint_url: str | None
    s3_bucket: str
    cv_uploaded_queue_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None,
        s3_bucket=os.getenv("S3_BUCKET", "goa-writing-files"),
        cv_uploaded_queue_url=os.getenv("CV_UPLOADED_QUEUE_URL", ""),
    )
