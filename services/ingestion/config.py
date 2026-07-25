from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    rag_service_url: str = 'http://rag:8084'
    openai_api_key: str = "mock-key"
    internal_api_key: str = "supersecret_internal_key_123"
    dry_run: bool = False
    embedding_base_url: str = "http://localhost:11434/v1"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    # Ollama ignores the key but the OpenAI SDK requires a non-empty string.
    # embedder.py reads this; without it every embedding call raised
    # AttributeError inside the handler and the document leg wrote nothing.
    embedding_api_key: str = "ollama"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()