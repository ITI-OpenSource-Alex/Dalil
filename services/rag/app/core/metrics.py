from prometheus_client import Histogram, Counter, Gauge

# Latency histogram in milliseconds
QUERY_LATENCY = Histogram(
    "goa_rag_query_latency_ms",
    "Latency of RAG queries in milliseconds",
    labelnames=["cache_hit"],
)
# Similarity score histogram
RETRIEVAL_SIMILARITY = Histogram(
    "goa_rag_retrieval_similarity_score",
    "Similarity scores of retrieved document chunks",
)
# Counter for low confidence queries
LOW_CONFIDENCE_TOTAL = Counter(
    "goa_rag_low_confidence_total",
    "Total number of low confidence RAG queries (similarity < 0.6)",
)


# GOA-033: the cross-encoder degrades to a token-overlap heuristic when the model
# cannot load -- which is what happens on the musl base image, since PyTorch has no
# musl build. A fallback nobody can see is a re-ranker that quietly stopped working,
# and a benchmark run in that state reports "rerank_enabled" while measuring
# something else entirely. Export the active mode instead of only logging it once.
RERANK_MODE = Gauge(
    "goa_rag_rerank_mode",
    "Active re-ranker: 1 = cross-encoder, 0 = degraded token-overlap fallback",
)
RERANK_FALLBACK_TOTAL = Counter(
    "goa_rag_rerank_fallback_total",
    "Re-rank calls served by the degraded fallback instead of the cross-encoder",
    labelnames=["cause"],  # model_unavailable | predict_failed
)


SCORING_PIPELINE_LATENCY = Histogram(
    "goa_scoring_pipeline_latency_ms",
    "Latency of the full GOA-012 scoring pipeline in milliseconds",
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000],
)
LLM_BOOST_VALUE = Histogram(
    "goa_scoring_llm_boost_value",
    "Distribution of the LLM boost values applied",
    buckets=list(range(-10, 12)),  # Creates buckets: [-10, -9, ... 10, 11]
)


CHECKLIST_GENERATED_TOTAL = Counter(
    "goa_rag_checklist_generated_total",
    "Total number of checklists generated, by source",
    labelnames=["source"],  # "llm" or "fallback"
)
CHECKLIST_GENERATION_LATENCY = Histogram(
    "goa_rag_checklist_generation_latency_ms",
    "Latency of checklist generation (LLM call or fallback) in milliseconds",
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000],
)
