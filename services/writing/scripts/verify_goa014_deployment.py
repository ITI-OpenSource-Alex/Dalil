"""Verify GOA-014 against deployed Writing, Langfuse, and Prometheus services."""

import argparse
import json
import math
import os
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EXPECTED_SPANS = {
    "writing-task_response",
    "writing-cohesion",
    "writing-vocabulary",
    "writing-grammar",
}
PLACEHOLDERS = {
    "",
    "your_anthropic_api_key",
    "your_langfuse_public_key",
    "your_langfuse_secret_key",
}


class VerificationError(RuntimeError):
    pass


def require_live_environment() -> None:
    missing = [
        name
        for name in (
            "ANTHROPIC_API_KEY",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_HOST",
        )
        if os.getenv(name, "").strip() in PLACEHOLDERS
    ]
    if missing:
        raise VerificationError(
            "Set real deployment values for: " + ", ".join(missing)
        )


def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise VerificationError(f"Unable to query {url}: {exc}") from exc


def _get_text(url: str) -> str:
    try:
        with urlopen(url, timeout=15) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except Exception as exc:
        raise VerificationError(f"Unable to query {url}: {exc}") from exc


def verify_writing_metrics(writing_url: str) -> None:
    metrics = _get_text(writing_url.rstrip("/") + "/metrics")
    required = {
        "goa_writing_agent_band_score",
        "goa_writing_evaluation_latency_ms",
        "goa_writing_cache_hit_rate",
    }
    missing = sorted(name for name in required if name not in metrics)
    if missing:
        raise VerificationError("Writing /metrics is missing: " + ", ".join(missing))


def _prometheus_value(prometheus_url: str, query: str) -> float:
    url = prometheus_url.rstrip("/") + "/api/v1/query?" + urlencode({"query": query})
    payload = _get_json(url)
    results = payload.get("data", {}).get("result", [])
    if payload.get("status") != "success" or not results:
        raise VerificationError(f"Prometheus returned no data for query: {query}")
    return float(results[0]["value"][1])


def verify_prometheus(prometheus_url: str, max_p95_ms: float) -> float:
    up = _prometheus_value(prometheus_url, 'up{job="writing"}')
    if up != 1:
        raise VerificationError("Prometheus Writing scrape target is not up")

    query = (
        "histogram_quantile(0.95, sum by (le) "
        "(rate(goa_writing_evaluation_latency_ms_bucket[5m])))"
    )
    p95_ms = _prometheus_value(prometheus_url, query)
    if math.isnan(p95_ms):
        raise VerificationError(
            "Prometheus has no recent evaluation samples; submit unique essays first"
        )
    if p95_ms >= max_p95_ms:
        raise VerificationError(
            f"Writing evaluation P95 is {p95_ms:.2f} ms; target is < {max_p95_ms:.0f} ms"
        )
    return p95_ms


def _metadata(item: Any) -> dict[str, Any]:
    value = getattr(item, "metadata", None)
    return value if isinstance(value, dict) else {}


def verify_langfuse(*, user_id: str | None, essay_id: int | None) -> str:
    from langfuse import Langfuse

    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )
    traces = client.fetch_traces(
        name="writing-evaluation-swarm",
        user_id=user_id,
        limit=25,
        order_by="timestamp.desc",
    ).data
    matching = [
        trace
        for trace in traces
        if essay_id is None or str(_metadata(trace).get("essay_id")) == str(essay_id)
    ]
    if not matching:
        raise VerificationError("No matching writing-evaluation-swarm trace found")

    trace = matching[0]
    observations = client.fetch_observations(trace_id=trace.id, limit=100).data
    criterion_spans = [item for item in observations if item.name in EXPECTED_SPANS]
    names = {item.name for item in criterion_spans}
    if len(criterion_spans) != 4 or names != EXPECTED_SPANS:
        raise VerificationError(
            f"Trace {trace.id} has criterion spans {sorted(names)}; expected exactly four"
        )

    required_metadata = {
        "criterion",
        "band_score",
        "prompt_tokens",
        "completion_tokens",
        "latency_ms",
    }
    for span in criterion_spans:
        missing = required_metadata - _metadata(span).keys()
        if missing:
            raise VerificationError(
                f"Span {span.name} is missing metadata: {sorted(missing)}"
            )
    return trace.id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify deployed GOA-014 Langfuse and Prometheus evidence"
    )
    parser.add_argument("--writing-url", default="http://localhost:8000")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--user-id")
    parser.add_argument("--essay-id", type=int)
    parser.add_argument("--max-p95-ms", type=float, default=30000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        require_live_environment()
        verify_writing_metrics(args.writing_url)
        trace_id = verify_langfuse(user_id=args.user_id, essay_id=args.essay_id)
        p95_ms = verify_prometheus(args.prometheus_url, args.max_p95_ms)
    except VerificationError as exc:
        print(f"GOA-014 verification failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ready",
                "langfuse_trace_id": trace_id,
                "prometheus_p95_ms": round(p95_ms, 2),
                "p95_target_ms": args.max_p95_ms,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
