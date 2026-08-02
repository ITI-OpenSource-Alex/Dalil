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

    # Long-term conversation memory (GOA-038).
    #
    # Every threshold here is configuration rather than a constant so tests can
    # drive the sweep without waiting for it: an integration test sets
    # memory_idle_minutes low and backdates a score, and the manual E2E runs with
    # memory_idle_minutes=1 so a human can watch the timer actually fire.
    memory_enabled: bool = True
    memory_idle_minutes: int = 30
    memory_sweep_interval_seconds: int = 300
    memory_sweep_batch_max: int = 20
    memory_fact_ttl_days: int = 30
    # Below this many turns there is nothing worth an LLM call. Without it every
    # abandoned "hi" costs a frontier-model extraction, which matters now that
    # inference is billed through AgentRouter.
    memory_min_turns: int = 4
    # Hard ceiling on the fact read that sits in front of classification. The
    # read is enrichment; a slow database must degrade the answer, never the turn.
    memory_load_timeout_ms: int = 250
    memory_cache_ttl_seconds: int = 300

    # Downstream Service URLs
    rag_service_url: str = "http://rag:8084"
    speaking_service_url: str = "http://speaking:8082"
    writing_service_url: str = "http://writing:8000"
    exam_service_url: str = "http://exam:8085"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    sqs_queue_name: str = "user-events-orchestration"

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
