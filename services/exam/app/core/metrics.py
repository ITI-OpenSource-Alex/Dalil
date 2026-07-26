from prometheus_client import Counter, Histogram


goa_speaking_exam_evaluations_total = Counter(
    "goa_speaking_exam_evaluations_total",
    "Total speaking exam evaluations requested",
    labelnames=["status"],
)


goa_speaking_exam_evaluation_ms = Histogram(
    "goa_speaking_exam_evaluation_ms",
    "Latency of speaking exam evaluations in milliseconds",
    labelnames=[],
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
    labelnames=["route"],
)

goa_exam_reading_sessions_total = Counter(
    "goa_exam_reading_sessions_total",
    "Total reading exam sessions started",
    labelnames=["exam_type"],
)

goa_exam_reading_score = Histogram(
    "goa_exam_reading_score",
    "Reading exam band score distribution",
    buckets=(4.0, 5.0, 6.0, 7.0, 8.0, 9.0),
)

goa_exam_listening_sessions_total = Counter(
    "goa_exam_listening_sessions_total",
    "Total listening exam sessions started",
    labelnames=["exam_type"],
)

goa_exam_listening_score = Histogram(
    "goa_exam_listening_score",
    "Listening exam band score distribution",
    buckets=(4.0, 5.0, 6.0, 7.0, 8.0, 9.0),
)

goa_exam_grading_latency_ms = Histogram(
    "goa_exam_grading_latency_ms",
    "Grading latency in milliseconds",
    labelnames=["skill_area"],
    buckets=(10, 50, 100, 250, 500),
)

goa_exam_history_requests_total = Counter(
    "goa_exam_history_requests_total",
    "Total requests to the exam history / progress / weak-area endpoints",
    labelnames=["endpoint"],
)
