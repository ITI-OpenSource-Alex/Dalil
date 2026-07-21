from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    port: int = 8084
    database_url: str
    anthropic_api_key: str = ""
    anthropic_auth_token: str = ""
    langfuse_public_key: Optional[str] = ""
    langfuse_secret_key: Optional[str] = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    internal_api_key: str = "supersecret_internal_key_123"
    # AWS / SQS Config AKA LocalStack
    AWS_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: str = "http://localstack:4566"
    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"
    SQS_QUEUE_NAME: str = "user-events"


    embedding_base_url: str = 'http://host.docker.internal:11434/v1'
    embedding_model: str = 'nomic-embed-text'
    embedding_api_key: str = 'ollama'

    anthropic_base_url: str = ""
    llm_model: str = "claude-opus-4-8"
    anthropic_user_agent: str = "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"

    
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
