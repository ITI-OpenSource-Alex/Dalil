from prometheus_client import Counter, Histogram

# Intent classification count counter (labeled by intent)
goa_orchestration_intent_classified_total = Counter(
    "goa_orchestration_intent_classified_total",
    "Total number of requests classified by intent",
    ["intent"]
)

# Intent classification latency histogram (explicit millisecond buckets)
goa_orchestration_classification_latency_ms = Histogram(
    "goa_orchestration_classification_latency_ms",
    "Latency of intent classification LLM call in milliseconds",
    buckets=[50, 100, 200, 500, 1000, 2000, 5000]
)

# Downstream latency histogram (explicit millisecond buckets, labeled by service)
goa_orchestration_downstream_latency_ms = Histogram(
    "goa_orchestration_downstream_latency_ms",
    "Latency of downstream service calls in milliseconds",
    ["service"],
    buckets=[50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000]
)



