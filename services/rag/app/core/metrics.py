from prometheus_client import Histogram, Counter
# Latency histogram in milliseconds
QUERY_LATENCY = Histogram(
    "goa_rag_query_latency_ms",
    "Latency of RAG queries in milliseconds",
    labelnames=["cache_hit"]
)
# Similarity score histogram
RETRIEVAL_SIMILARITY = Histogram(
    "goa_rag_retrieval_similarity_score",
    "Similarity scores of retrieved document chunks"
)
# Counter for low confidence queries
LOW_CONFIDENCE_TOTAL = Counter(
    "goa_rag_low_confidence_total",
    "Total number of low confidence RAG queries (similarity < 0.6)"
)