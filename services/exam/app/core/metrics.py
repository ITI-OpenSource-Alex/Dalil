from prometheus_client import Counter, Histogram



goa_speaking_exam_evaluations_total = Counter(
    "goa_speaking_exam_evaluations_total",
    "Total speaking exam evaluations requested",
    labelnames = [
        "status"
    ]
)


goa_speaking_exam_evaluation_ms = Histogram(
    "goa_speaking_exam_evaluation_ms",
    "Latency of speaking exam evaluations in milliseconds",
    labelnames = []
)


goa_writing_exam_task1_evaluation_ms = Histogram(
    "goa_writing_exam_task1_evaluation_ms",
    "Latency of writing exam task 1 evaluations in milliseconds",
    labelnames=[],
)

goa_writing_exam_task2_evaluation_ms = Histogram(
    "goa_writing_exam_task2_evaluation_ms",
    "Latency of writing exam task 2 evaluations in milliseconds",
    labelnames=[],
)

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
