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

# GOA-045: the curated FAQ short-circuit.
#
# Three counters rather than one, because "the FAQ is working" and "the FAQ is
# being bypassed correctly" are different questions and only one of them is
# visible from a hit count. A sudden collapse in hits with a matching rise in
# bypasses means the volatility classifier got broader; a collapse with no rise
# means matching itself broke.
FAQ_HITS_TOTAL = Counter(
    "goa_faq_hits_total",
    "Curated FAQ answers served without embedding, retrieval, or an LLM call",
    labelnames=["category"],
)
FAQ_BYPASS_TOTAL = Counter(
    "goa_faq_bypass_total",
    "Questions routed past the FAQ because their answer is source-sensitive",
    labelnames=["reason"],  # amount | proof_of_funds | deadline | eligibility | processing_time
)
# A stale entry is a silent failure: the answer is still there and still
# plausible, it has just aged past the point anyone vouched for it. Counting
# suppressions is what turns "nobody has reviewed the FAQ in a year" from an
# invisible state into an alertable one.
FAQ_STALE_SUPPRESSED_TOTAL = Counter(
    "goa_faq_stale_suppressed_total",
    "FAQ matches suppressed because the entry is past its review window",
)
