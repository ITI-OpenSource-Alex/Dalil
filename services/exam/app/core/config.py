from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8085
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
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
