from prometheus_client import Histogram, Counter

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
