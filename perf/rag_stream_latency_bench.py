"""Measure user-visible milestones on the updated Ask Dalil streaming path.

The benchmark is deliberately sequential: it measures one interactive user's
latency without manufacturing provider queueing through local concurrency.
It uses only the Python standard library so it can run from a clean host.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import uuid
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit


QUESTIONS = [
    "What proof of funds is required for a German student visa?",
    "What IELTS score is commonly required for computer science master's programmes in Germany?",
    "Which application documents are normally required for a master's degree in Germany?",
    "What scholarships are available to international master's students in Germany?",
    "How does the uni-assist application process work for international students?",
    "Are public universities in Germany tuition-free for international master's students?",
    "What TOEFL score is commonly required by German universities for English-taught master's programmes?",
    "When should an international student start applying for a German master's programme?",
]

# Every question below satisfies orchestration's conservative deterministic RAG
# predicate.  Keeping this list separate prevents an end-to-end RAG benchmark
# from accidentally measuring another product route such as opportunity matching.
CHAT_RAG_QUESTIONS = [
    "What proof of funds is required for a German student visa?",
    "What IELTS score is required by German universities?",
    "What TOEFL score is required by German universities?",
    "Are public universities in Germany tuition-free?",
    "What is the application deadline for German university programmes?",
    "Which university admission documents are required in Germany?",
    "How much tuition do German universities charge international students?",
    "What GPA is required for admission to German universities?",
    "What ECTS requirements apply to German university programmes?",
    "Can a German student visa require a blocked account?",
]


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(samples: list[dict]) -> dict:
    metric_names = [
        "headers_ms",
        "first_event_ms",
        "first_status_ms",
        "routing_status_ms",
        "retrieving_status_ms",
        "generating_status_ms",
        "metadata_ms",
        "first_token_ms",
        "sources_ms",
        "total_ms",
    ]
    summary = {
        "runs": len(samples),
        "successful_runs": sum(1 for sample in samples if sample.get("ok")),
        "delivery_failures": sum(1 for sample in samples if not sample.get("ok")),
        "errors": [sample.get("error") for sample in samples if sample.get("error")],
    }
    for metric in metric_names:
        values = [
            float(sample[metric])
            for sample in samples
            if sample.get("ok") and sample.get(metric) is not None
        ]
        if not values:
            continue
        summary[metric] = {
            "min": round(min(values), 1),
            "p50": round(statistics.median(values), 1),
            "p95": round(percentile(values, 0.95), 1),
            "max": round(max(values), 1),
        }
    return summary


def _event_blocks(response):
    event_name = None
    data_lines = []
    while True:
        raw = response.readline()
        if not raw:
            if data_lines:
                yield event_name, "\n".join(data_lines)
            return
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())


def measure_stream(
    *, url: str, payload: dict, headers: dict, timeout: float, label: str
) -> dict:
    parsed = urlsplit(url)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    body = json.dumps(payload).encode("utf-8")
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Content-Length": str(len(body)),
        **headers,
    }
    started = time.perf_counter()
    sample = {
        "label": label,
        "status_code": None,
        "ok": False,
        "headers_ms": None,
        "first_event_ms": None,
        "first_status_ms": None,
        "routing_status_ms": None,
        "retrieving_status_ms": None,
        "generating_status_ms": None,
        "metadata_ms": None,
        "first_token_ms": None,
        "sources_ms": None,
        "total_ms": None,
        "token_events": 0,
        "answer_chars": 0,
        "events": [],
        "error": None,
    }
    try:
        connection.request("POST", parsed.path, body=body, headers=request_headers)
        response = connection.getresponse()
        sample["status_code"] = response.status
        sample["headers_ms"] = round((time.perf_counter() - started) * 1000, 1)
        if response.status != 200:
            detail = response.read(500).decode("utf-8", errors="replace")
            sample["error"] = f"HTTP {response.status}: {detail}"
            return sample

        for event_name, event_data in _event_blocks(response):
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            try:
                event = json.loads(event_data)
            except json.JSONDecodeError:
                event = {"type": event_name, "raw": event_data[:200]}
            event_type = event.get("type") or event_name or "unknown"
            sample["events"].append(event_type)
            if sample["first_event_ms"] is None:
                sample["first_event_ms"] = elapsed_ms
            if event_type == "status":
                if sample["first_status_ms"] is None:
                    sample["first_status_ms"] = elapsed_ms
                stage = event.get("stage")
                key = f"{stage}_status_ms"
                if key in sample and sample[key] is None:
                    sample[key] = elapsed_ms
            elif event_type == "metadata" and sample["metadata_ms"] is None:
                sample["metadata_ms"] = elapsed_ms
            elif event_type == "token":
                sample["token_events"] += 1
                sample["answer_chars"] += len(event.get("content") or "")
                if sample["first_token_ms"] is None:
                    sample["first_token_ms"] = elapsed_ms
            elif event_type == "sources" and sample["sources_ms"] is None:
                sample["sources_ms"] = elapsed_ms
            elif event_type == "error":
                sample["error"] = event.get("error") or "stream error"

        sample["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        sample["ok"] = sample["error"] is None and sample["first_token_ms"] is not None
        return sample
    except Exception as exc:  # benchmark must preserve partial timing evidence
        sample["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        sample["error"] = f"{type(exc).__name__}: {exc}"
        return sample
    finally:
        connection.close()


def _unique_question(question: str, run_id: str, index: int) -> str:
    return f"{question} [benchmark {run_id}-{index}]"


def run_phase(
    *,
    phase: str,
    count: int,
    url: str,
    payload_factory,
    headers: dict,
    timeout: float,
) -> list[dict]:
    samples = []
    for index in range(count):
        sample = measure_stream(
            url=url,
            payload=payload_factory(index),
            headers=headers,
            timeout=timeout,
            label=f"{phase}-{index + 1}",
        )
        samples.append(sample)
        print(
            f"{sample['label']}: status={sample['status_code']} "
            f"first_event={sample['first_event_ms']}ms "
            f"first_token={sample['first_token_ms']}ms "
            f"total={sample['total_ms']}ms error={sample['error']}"
        )
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rag-url", default="http://127.0.0.1:8084/query/stream")
    parser.add_argument("--chat-url", default="http://127.0.0.1:8083/chat")
    parser.add_argument("--cold-runs", type=int, default=8)
    parser.add_argument("--cache-runs", type=int, default=5)
    parser.add_argument("--chat-runs", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cold_samples = run_phase(
        phase="rag_cold",
        count=args.cold_runs,
        url=args.rag_url,
        payload_factory=lambda index: {
            "question": _unique_question(
                QUESTIONS[index % len(QUESTIONS)], run_id, index
            ),
            "userId": str(uuid.uuid4()),
            "topK": 5,
        },
        headers={"X-Correlation-Id": f"bench-rag-{run_id}"},
        timeout=args.timeout,
    )

    repeated_question = (
        "What proof of funds is required for a German student visa? "
        f"[cache benchmark {run_id}]"
    )
    cache_user = str(uuid.uuid4())
    cache_seed = []
    if args.cache_runs:
        cache_seed = run_phase(
            phase="rag_cache_seed",
            count=1,
            url=args.rag_url,
            payload_factory=lambda _index: {
                "question": repeated_question,
                "userId": cache_user,
                "topK": 5,
            },
            headers={"X-Correlation-Id": f"bench-cache-seed-{run_id}"},
            timeout=args.timeout,
        )
    cache_samples = run_phase(
        phase="rag_cache_hit",
        count=args.cache_runs,
        url=args.rag_url,
        payload_factory=lambda _index: {
            "question": repeated_question,
            "userId": cache_user,
            "topK": 5,
        },
        headers={"X-Correlation-Id": f"bench-cache-hit-{run_id}"},
        timeout=args.timeout,
    )

    chat_samples = run_phase(
        phase="chat_cold",
        count=args.chat_runs,
        url=args.chat_url,
        payload_factory=lambda index: {
            "message": _unique_question(
                CHAT_RAG_QUESTIONS[index % len(CHAT_RAG_QUESTIONS)],
                f"chat-{run_id}",
                index,
            ),
            "userId": str(uuid.uuid4()),
            "sessionId": str(uuid.uuid4()),
        },
        headers={
            "X-Correlation-Id": f"bench-chat-{run_id}",
            "X-Subscription-Tier": "free",
        },
        timeout=args.timeout,
    )

    phases = {
        "rag_cold": cold_samples,
        "rag_cache_seed": cache_seed,
        "rag_cache_hit": cache_samples,
        "chat_cold": chat_samples,
    }
    segments = {
        "rag_cold_generated": [
            sample for sample in cold_samples
            if sample.get("generating_status_ms") is not None
        ],
        "rag_cold_refusal": [
            sample for sample in cold_samples
            if sample.get("generating_status_ms") is None
        ],
        "chat_fast_route": [
            sample for sample in chat_samples
            if sample.get("metadata_ms") is not None
            and sample["metadata_ms"] < 1000
        ],
        "chat_model_route": [
            sample for sample in chat_samples
            if sample.get("metadata_ms") is not None
            and sample["metadata_ms"] >= 1000
        ],
    }
    report = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "sequential": True,
            "cold_cache_strategy": "unique question and user ID per sample",
            "cache_hit_strategy": "identical question and user ID after one seed",
            "timeout_seconds": args.timeout,
            "rag_url": args.rag_url,
            "chat_url": args.chat_url,
        },
        "summaries": {
            name: summarize(samples)
            for name, samples in {**phases, **segments}.items()
        },
        "samples": phases,
    }
    output = Path(args.output) if args.output else Path(
        f"perf/reports/{run_id}-rag-stream-latency.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report={output}")

    failures = sum(
        1 for samples in phases.values() for sample in samples if not sample["ok"]
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
