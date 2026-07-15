from prometheus_client import Counter, Gauge

# Prometheus Metrics Definitions
DOCS_PROCESSED_TOTAL = Counter(
    "goa_ingestion_docs_processed_total",
    "Total number of documents processed during ingestion",
    ["source", "outcome"] # outcome: 'success', 'skip', 'fail'
)

EMBEDDING_TOKENS_TOTAL = Counter(
    "goa_ingestion_embedding_tokens_total",
    "Total number of tokens used for embeddings during ingestion",
    ["source"]
)

RUN_DURATION_SECONDS = Gauge(
    "goa_ingestion_run_duration_seconds",
    "Duration of the ingestion run in seconds"
)