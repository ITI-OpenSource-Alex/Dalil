from prometheus_client import Counter, Histogram

goa_exam_sessions_total = Counter(
    "goa_exam_sessions_total",
    "Total completed GOA exam sessions",
    labelnames=[
        "skill_area",
        "exam_type",
        "outcome",
    ],
)
EXAM_REQUEST_LATENCY = Histogram(
    "goa_exam_request_latency_ms",
    "Latency of exam service requests in milliseconds",
    labelnames=["route"]
)
