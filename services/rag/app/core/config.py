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
    # Local development may set an endpoint and static credentials. In AWS,
    # leaving these unset makes the SDK use the ECS task role.
    AWS_REGION: str = "eu-west-1"
    AWS_ENDPOINT_URL: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    SQS_QUEUE_NAME: str = "user-events-rag"


    embedding_base_url: str = 'http://host.docker.internal:11434/v1'
    embedding_model: str = 'nomic-embed-text'
    embedding_api_key: str = 'ollama'

    anthropic_base_url: str = ""
    llm_model: str = "claude-opus-4-8"
    anthropic_user_agent: str = "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"



    rag_rerank_enabled: bool = True
    rag_threshold_enabled: bool = True
    rag_cache_enabled: bool = True
    rag_retrieval_width: int = 15
    rag_ivfflat_probes: int = 1
    confidence_threshold: float = 0.60


    
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
