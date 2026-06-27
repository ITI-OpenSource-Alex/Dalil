from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    port: int = 8083
    database_url: str
    redis_url: str
    anthropic_api_key: str
    internal_api_key: str = "supersecret_internal_key_123"
    otel_service_name: str = "orchestration"
    
    # Langfuse Observability
    langfuse_public_key: Optional[str] = ""
    langfuse_secret_key: Optional[str] = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    
    # Downstream Service URLs
    rag_service_url: str = "http://rag:8084"
    speaking_service_url: str = "http://speaking:8082"
    writing_service_url: str = "http://writing:8000"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
settings = Settings()

