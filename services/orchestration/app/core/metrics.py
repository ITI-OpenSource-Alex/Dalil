from prometheus_client import Counter, Histogram, Gauge

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

# Circuit breaker state gauge (labeled by service)
goa_orchestration_circuit_breaker_state = Gauge(
    "goa_orchestration_circuit_breaker_state",
    "Circuit breaker state for downstream services (0=closed, 1=open)",
    ["service"]
)

# --------------------------------------------------------------------------
# Long-term conversation memory (GOA-038)
#
# The sweep runs unattended, off the request path, on a frontier model that is
# now genuinely billed. Without these, "extraction quietly stopped working" and
# "extraction is quietly spending money" both look exactly like silence.
# --------------------------------------------------------------------------

goa_orchestration_facts_extracted_total = Counter(
    "goa_orchestration_facts_extracted_total",
    "Facts written to long-term memory, by type",
    ["fact_type"]
)

# resolution: created | reinforced | replaced | discarded
goa_orchestration_facts_conflicts_total = Counter(
    "goa_orchestration_facts_conflicts_total",
    "How incoming facts resolved against what was already stored",
    ["resolution"]
)

# reason: too_long | injection | pii | invalid_type
goa_orchestration_facts_rejected_total = Counter(
    "goa_orchestration_facts_rejected_total",
    "Extracted values refused by the sanitizer before storage",
    ["reason"]
)

goa_orchestration_facts_extraction_failures_total = Counter(
    "goa_orchestration_facts_extraction_failures_total",
    "Sessions whose fact extraction failed outright"
)

goa_orchestration_facts_extraction_latency_ms = Histogram(
    "goa_orchestration_facts_extraction_latency_ms",
    "Latency of the fact-extraction LLM call in milliseconds",
    buckets=[500, 1000, 2000, 5000, 10000, 30000]
)

goa_orchestration_facts_sweep_candidates = Gauge(
    "goa_orchestration_facts_sweep_candidates",
    "Idle sessions found by the most recent sweep"
)

# source: cache | db | miss -- 'miss' covers the database being unreachable,
# which must degrade the answer rather than fail the turn.
goa_orchestration_facts_loaded_total = Counter(
    "goa_orchestration_facts_loaded_total",
    "Fact loads on the request path, by where they were served from",
    ["source"]
)

goa_orchestration_facts_load_latency_ms = Histogram(
    "goa_orchestration_facts_load_latency_ms",
    "Latency of loading a user's facts on the chat critical path",
    buckets=[1, 5, 10, 25, 50, 100, 250]
)
