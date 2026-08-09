from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8085
    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    sqs_queue_name: str = "user-events-exam"
    database_url: str
    internal_api_key: str
    langfuse_public_key: Optional[str] = ""
    langfuse_secret_key: Optional[str] = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    speaking_service_url: str
    writing_service_url: str
    aws_region: str = "us-east-1"
    s3_region: Optional[str] = None
    aws_endpoint_url: Optional[str] = None
    s3_bucket: str = "goa-exam-audio"
    # Bucket holding Academic Writing Task 1 stimulus images (GOA-XXX). Kept
    # separate from s3_bucket (listening audio) so the two never collide.
    writing_image_bucket: str = "goa-writing-files"
    # Endpoint used only for *pre-signing* browser-facing URLs. aws_endpoint_url
    # is the internal S3 host (http://localstack:4566) that server-to-server
    # boto calls use; a URL signed against it cannot be resolved by a browser
    # (BUG-016). When set, this public host is signed instead so the signature is
    # valid for the address the browser actually requests. Falls back to
    # aws_endpoint_url when unset, so tests and non-browser flows are unaffected.
    s3_public_endpoint_url: Optional[str] = None
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

