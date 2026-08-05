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
    # GOA-134. Must stay ABOVE the speaking service's own swarm budget
    # (swarmEvaluationTimeout, 60s in services/speaking/internal/speaking/client.go),
    # or this client aborts a holistic evaluation that was going to succeed and the
    # session is reverted for no reason. It was a hardcoded 30.0 against a 15s inner
    # deadline; both were below the measured p95 time-to-first-criterion of 28.7s.
    # test_speaking_client_timeout_exceeds_speaking_budget pins the relationship.
    speaking_evaluation_timeout_s: float = 75.0
    writing_service_url: str
    aws_region: str = "us-east-1"
    s3_region: Optional[str] = None
    aws_endpoint_url: Optional[str] = None
    s3_bucket: str = "goa-exam-audio"
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

