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
    
    
    anthropic_base_url: str = ""
    anthropic_auth_token: str = ""
    anthropic_user_agent: str = "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
    llm_model: str = "claude-opus-4-8"


    # Downstream Service URLs
    rag_service_url: str = "http://rag:8084"
    speaking_service_url: str = "http://speaking:8082"
    writing_service_url: str = "http://writing:8000"

    # Browser-facing URLs. The two above are Docker hostnames used for
    # server-to-server calls; handing them to a client produced
    # ws://speaking:8082/ws and http://writing:8000/... which no browser can
    # resolve (BUG-016).
    #
    # Writing's SSE now goes through the Gateway, so it inherits JWT auth, rate
    # limiting and correlation IDs. Speaking's WebSocket does not yet -- the
    # Gateway has no WS proxy (BUG-029 / GOA-094), so it is published directly
    # for now and tracked as a follow-up.
    public_gateway_url: str = "http://localhost:8080"
    public_speaking_ws_url: str = "ws://localhost:8082/ws"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
settings = Settings()

