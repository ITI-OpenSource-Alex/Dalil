from threading import Lock

from prometheus_client import Counter, Gauge, Histogram


AGENT_BAND_SCORE = Histogram(
    "goa_writing_agent_band_score",
    "IELTS band scores returned by writing evaluation agents",
    labelnames=["criterion"],
    buckets=[value / 2 for value in range(19)],
)

EVALUATION_LATENCY_MS = Histogram(
    "goa_writing_evaluation_latency_ms",
    "Wall-clock latency for a four-agent writing evaluation in milliseconds",
    buckets=[100, 250, 500, 1000, 2500, 5000, 10000, 15000, 20000, 30000, 60000],
)

goa_writing_exam_evaluation_ms = Histogram(
    "goa_writing_exam_evaluation_ms",
    "Wall-clock latency for an exam-task writing evaluation in milliseconds",
    labelnames=["task_type"],
    buckets=[100, 250, 500, 1000, 2500, 5000, 10000, 15000, 20000, 30000, 60000],
)

CV_EXTRACTION_DURATION_MS = Histogram(
    "goa_cv_extraction_duration_ms",
    "Wall-clock CV extraction duration in milliseconds",
    buckets=[25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000],
)

CV_EXTRACTION_TOTAL = Counter(
    "goa_cv_extraction_total",
    "CV extraction invocations by outcome",
    labelnames=["outcome"],
)

CACHE_HIT_RATE = Gauge(
    "goa_writing_cache_hit_rate",
    "Ratio of cached writing evaluations to all writing evaluation requests",
)

# GOA-135. A model missing from the shared price table records a null cost rather
# than 0.0, and without this counter that null looks like "no LLM calls" instead
# of "we do not know what these cost".
UNPRICED_MODEL_TOTAL = Counter(
    "goa_writing_unpriced_model_total",
    "LLM calls whose model is missing from the shared price table",
    labelnames=["model"],
)


class CacheHitTracker:
    """Process-local request counters used to publish the requested ratio gauge."""

    def __init__(self) -> None:
        self._hits = 0
        self._requests = 0
        self._lock = Lock()

    def record(self, *, hit: bool) -> float:
        with self._lock:
            self._requests += 1
            if hit:
                self._hits += 1
            ratio = self._hits / self._requests
            CACHE_HIT_RATE.set(ratio)
            return ratio

    def reset(self) -> None:
        with self._lock:
            self._hits = 0
            self._requests = 0
            CACHE_HIT_RATE.set(0)


cache_hit_tracker = CacheHitTracker()