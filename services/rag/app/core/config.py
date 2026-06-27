from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    port: int = 8084
    database_url: str
    openai_api_key: str
    anthropic_api_key: str
    langfuse_public_key: Optional[str] = ""
    langfuse_secret_key: Optional[str] = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    internal_api_key: str = "supersecret_internal_key_123"

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
