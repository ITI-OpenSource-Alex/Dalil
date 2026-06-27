from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    rag_service_url: str = 'http://rag:8084'
    openai_api_key: str = "mock-key"
    internal_api_key: str = "supersecret_internal_key_123"
    dry_run: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()