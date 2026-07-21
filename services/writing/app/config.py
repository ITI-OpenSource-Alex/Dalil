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
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    writing_model: str = "claude-opus-4-8"
    anthropic_timeout_seconds: float = 25.0
    openai_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    cache_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None,
        s3_bucket=os.getenv("S3_BUCKET", "goa-writing-files"),
        cv_uploaded_queue_url=os.getenv("CV_UPLOADED_QUEUE_URL", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", ""),
        writing_model=os.getenv("WRITING_MODEL", "claude-opus-4-8"),
        anthropic_timeout_seconds=float(
            os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "25")
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        langfuse_host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        cache_version=os.getenv("WRITING_CACHE_VERSION", "v1"),
    )
