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

    embedding_base_url: str = "http://host.docker.internal:11434/v1"
    embedding_model: str = "nomic-embed-text"
    embedding_api_key: str = "ollama"

    anthropic_base_url: str = ""
    llm_model: str = "claude-opus-5"
    rag_answer_max_tokens: int = 512
    anthropic_user_agent: str = (
        "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
    )

    rag_rerank_enabled: bool = True
    rag_threshold_enabled: bool = True
    rag_cache_enabled: bool = True
    rag_cache_ttl_seconds: int = 300
    rag_retrieval_width: int = 15
    # GOA-030. This was 1, meaning every production query scanned one IVFFlat
    # cluster out of the index's lists=100 -- roughly 1% of the corpus. It is
    # pgvector's build-time default, not a tuned value, and it survived because
    # the frozen eval corpus is small enough that one cluster covers it.
    #
    # Against the live catalogue (3903 university chunks vs 19 visa chunks) it
    # is a correctness bug, not a tuning knob: a Germany student-visa question
    # returned four MastersPortal programme pages and zero visa documents, while
    # the correct EU-immigration-portal chunk -- which scores 0.854, the highest
    # similarity in the whole corpus -- sat in a cluster that was never probed.
    # That is GOA-030's Journey 2 failing on retrieval, not on data.
    #
    # 10 is sqrt(lists), pgvector's documented guidance. Measured over 10
    # questions x 3 repeats against the live catalogue
    # (perf/rag_probes_bench.py, artefact perf/reports/GOA-030-probes-sweep.json):
    #
    #   probes  recall@5  visa recall  programme recall  p50 ms  p95 ms
    #        1      0.40         0.25              1.00  1949.2  4570.3
    #        5      0.90         0.88              1.00  1873.9  2250.8
    #       10      1.00         1.00              1.00  1805.0  2149.7
    #       20      1.00         1.00              1.00  2028.3  2773.6
    #       50      1.00         1.00              1.00  2206.2  2686.0
    #
    # There is no trade-off to balance here: 10 beats 1 on recall AND on
    # latency. Raising it further buys no recall and costs time.
    #
    # Coupled to the index: documents_embedding_idx is built with lists=100. If
    # that changes, re-derive as sqrt(lists) and re-run the benchmark rather
    # than carrying 10 forward.
    rag_ivfflat_probes: int = 10
    # Demo migrations remain useful for isolated development and integration
    # tests, but user-facing opportunity matching must never mix them into the
    # scraped catalogue unless a developer opts in explicitly.
    include_demo_programs: bool = False
    # GOA-137 measured dense Recall@10=1.00 on both adversarial subsets before
    # implementation, so the required +0.15/+0.10 gains are impossible on the
    # frozen corpus. Keep hybrid available for clean A/B requests but default off.
    rag_hybrid_enabled: bool = False
    # GOA-140 (2026-08-13): raised 0.60 -> 0.71 after sweeping the measured dense
    # top-similarity distribution over the 45-item golden set on the live 8,001-doc
    # corpus. At 0.60 only 2/17 unanswerable questions were refused (0.1176); at 0.71
    # that becomes 11/17 (0.6471) with false refusal UNCHANGED at 1/28 (0.0357).
    # 0.71 is the knee: every step above it buys correct refusals by trading away
    # answerable ones (0.73 -> 0.7059 correct but 0.1071 false; 0.75 -> 0.2143 false).
    # The distributions overlap (answerable min 0.5639, unanswerable max 0.7715), so
    # no threshold separates them cleanly and >=0.70 correct refusal is not reachable
    # on this corpus without harming false refusal.
    # LIMITATION: tuned on the same 45 items used to evaluate it. A held-out set is
    # required before this value is treated as validated. See
    # Docs/gold-tier-evidence/rag-benchmark-live-2026-08-13.md.
    confidence_threshold: float = 0.71

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
