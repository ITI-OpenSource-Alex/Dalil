from __future__ import annotations

import json
import math
import os
import platform
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from anthropic import Anthropic


REPO_ROOT = Path(os.environ.get("GOA_REPO_ROOT", "/workspace"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "packages" / "pricing" / "py") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "pricing" / "py"))

from evals import judge, runner  # noqa: E402
from goa_pricing import cost_usd  # noqa: E402


PHASE = os.environ.get("GOA_BENCH_PHASE", "pre")
REPEATS = int(os.environ.get("GOA_BENCH_REPEATS", "5"))
WRITING_URL = os.environ.get("WRITING_SERVICE_URL", "http://writing:8000")
WRITING_TIMEOUT_SECONDS = float(
    os.environ.get("GOA_BENCH_WRITING_TIMEOUT_SECONDS", "600")
)
SAME_FAMILY_MODEL = "claude-opus-5"
INDEPENDENT_MODEL = "gpt-5.6-sol"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return round(ordered[index], 3)


def summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "std_dev": None,
            "max_spread": None,
            "modal_band": None,
            "modal_tie": None,
        }
    modes = statistics.multimode(values)
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4),
        "std_dev": round(statistics.pstdev(values), 4),
        "max_spread": round(max(values) - min(values), 4),
        "modal_band": modes[0],
        "modal_tie": len(modes) > 1,
    }


def normalize_agent_result(payload: dict[str, Any]) -> dict[str, Any]:
    return runner._normalise_agent_result(payload)


def provenance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sources = sorted({row.get("band_source") for row in rows if row.get("band_source")})
    return {
        "n_total": len(rows),
        "n_validated": sum(row.get("label_validated") is True for row in rows),
        "n_synthetic": sum(row.get("label_validated") is False for row in rows),
        "band_source": sources,
    }


def serialize_verdict(verdict: judge.JudgeVerdict) -> dict[str, Any]:
    raw = asdict(verdict)
    for key in ("agent_band", "delta"):
        if isinstance(raw.get(key), float) and math.isnan(raw[key]):
            raw[key] = None
    return raw


class OpenAIJudgeClient:
    """Expose AgentRouter's OpenAI endpoint through judge.py's messages interface."""

    def __init__(self) -> None:
        token = os.environ.get("EVAL_JUDGE_API_KEY") or os.environ.get(
            "ANTHROPIC_AUTH_TOKEN", ""
        )
        if not token:
            raise RuntimeError("no judge API key configured")
        base_url = os.environ.get("EVAL_JUDGE_BASE_URL", "https://agentrouter.org/v1")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": os.environ.get("ANTHROPIC_USER_AGENT")
            or "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14",
        }
        self.messages = self

    def create(self, *, model: str, max_tokens: int, messages: list[dict], **_: Any):
        response = httpx.post(
            self.url,
            headers=self.headers,
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "stream": False,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        payload = response.json()
        choice = payload["choices"][0]["message"]
        content = choice.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not content:
            raise ValueError(f"judge response carried no content: {str(payload)[:300]}")
        usage = payload.get("usage") or {}
        return SimpleNamespace(
            content=[SimpleNamespace(text=content)],
            usage=SimpleNamespace(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
        )


def same_family_judge_client() -> Anthropic:
    """Use the production Anthropic route with a benchmark-sized read budget."""
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get(
        "ANTHROPIC_API_KEY", ""
    )
    if not token:
        raise RuntimeError("no same-family judge API key configured")
    return Anthropic(
        api_key=token,
        base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
        timeout=float(os.environ.get("GOA_BENCH_JUDGE_TIMEOUT_SECONDS", "180")),
        max_retries=0,
        default_headers={
            "User-Agent": os.environ.get("ANTHROPIC_USER_AGENT")
            or "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
        },
    )


def call_writing(item: dict[str, Any], repeat: int, nonce: str) -> dict[str, Any]:
    submission_type = f"typed_text_goa136_{nonce}_{repeat}"
    payload = {
        "userId": f"goa136-{PHASE}-{nonce}",
        "essayText": item["essay"],
        "submissionType": submission_type,
        "examType": "IELTS Writing",
    }
    started = time.perf_counter()
    response = httpx.post(
        f"{WRITING_URL.rstrip('/')}/essays/evaluate",
        json=payload,
        timeout=WRITING_TIMEOUT_SECONDS,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    body = response.json()
    if body.get("overall_band") is None:
        raise ValueError(f"response carried no overall_band: {str(body)[:300]}")
    return {
        "item_id": item["id"],
        "repeat": repeat,
        "elapsed_ms": round(elapsed_ms, 3),
        "from_cache": body.get("from_cache"),
        "result": normalize_agent_result(body),
    }


def consistency(raw_runs: list[dict[str, Any]]) -> dict[str, Any]:
    per_item: dict[str, Any] = {}
    for item_id in sorted({row["item_id"] for row in raw_runs}):
        rows = [row for row in raw_runs if row["item_id"] == item_id]
        bands = [float(row["result"]["overall_band"]) for row in rows]
        criteria: dict[str, Any] = {}
        criterion_names = sorted(
            {name for row in rows for name in (row["result"].get("criteria") or {})}
        )
        for name in criterion_names:
            values = [
                float(row["result"]["criteria"][name])
                for row in rows
                if name in (row["result"].get("criteria") or {})
            ]
            criteria[name] = summary(values)
        per_item[item_id] = {
            **summary(bands),
            "unanimous": len(set(bands)) == 1,
            "criteria": criteria,
        }

    item_stats = list(per_item.values())
    all_bands = [
        float(row["result"]["overall_band"])
        for row in raw_runs
    ]
    domain = {
        "n_items": len(item_stats),
        "repeats": REPEATS,
        "mean": round(statistics.mean(all_bands), 4) if all_bands else None,
        "std_dev": round(statistics.mean(row["std_dev"] for row in item_stats), 4)
        if item_stats
        else None,
        "std_dev_definition": "mean of per-item population standard deviations",
        "max_spread": max((row["max_spread"] for row in item_stats), default=None),
        "unanimous_rate": round(
            sum(row["unanimous"] for row in item_stats) / len(item_stats), 4
        )
        if item_stats
        else None,
    }

    criterion_names = sorted(
        {name for row in item_stats for name in row["criteria"]}
    )
    domain["criteria"] = {}
    for name in criterion_names:
        available = [row["criteria"][name] for row in item_stats if name in row["criteria"]]
        domain["criteria"][name] = {
            "std_dev": round(statistics.mean(row["std_dev"] for row in available), 4),
            "std_dev_definition": "mean of per-item population standard deviations",
            "max_spread": max(row["max_spread"] for row in available),
            "unanimous_rate": round(
                sum(row["max_spread"] == 0 for row in available) / len(available), 4
            ),
        }
    return {"per_item": per_item, "domain": domain}


def judge_arm(
    model: str,
    items: list[dict[str, Any]],
    agent_results: list[dict[str, Any]],
) -> dict[str, Any]:
    os.environ["EVAL_JUDGE_MODEL"] = model
    client = (
        OpenAIJudgeClient()
        if model == INDEPENDENT_MODEL
        else same_family_judge_client()
    )
    started = time.perf_counter()
    verdicts = judge.judge_all(
        "writing", items, agent_results, client=client, max_workers=1
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    accuracy = runner.compute_accuracy(verdicts)
    mae = runner.compute_mae(verdicts, domain="writing")
    input_tokens = accuracy["input_tokens"]
    output_tokens = accuracy["output_tokens"]
    return {
        "model": model,
        "accuracy": accuracy,
        "mae": mae,
        "elapsed_ms": round(elapsed_ms, 3),
        "incremental_cost_usd": cost_usd(model, input_tokens, output_tokens),
        "verdicts": [serialize_verdict(verdict) for verdict in verdicts],
    }


def family_delta(same: dict[str, Any], independent: dict[str, Any]) -> dict[str, Any]:
    same_by_id = {row["item_id"]: row for row in same["verdicts"]}
    independent_by_id = {row["item_id"]: row for row in independent["verdicts"]}
    changed = []
    judged_band_deltas = {}
    for item_id in sorted(same_by_id):
        left = same_by_id[item_id]
        right = independent_by_id[item_id]
        if left["verdict"] != right["verdict"]:
            changed.append(item_id)
        if left["judged_band"] is not None and right["judged_band"] is not None:
            judged_band_deltas[item_id] = round(
                right["judged_band"] - left["judged_band"], 3
            )
        else:
            judged_band_deltas[item_id] = None
    return {
        "accuracy_delta": (
            independent["accuracy"]["accuracy"] - same["accuracy"]["accuracy"]
            if independent["accuracy"]["accuracy"] is not None
            and same["accuracy"]["accuracy"] is not None
            else None
        ),
        "mae_delta": (
            independent["mae"]["overall"] - same["mae"]["overall"]
            if independent["mae"]["overall"] is not None
            and same["mae"]["overall"] is not None
            else None
        ),
        "verdicts_changed": len(changed),
        "changed_item_ids": changed,
        "judged_band_deltas": judged_band_deltas,
        "note": (
            "accuracy and verdict are computed in code from agent_band versus "
            "expert_band; judge family can change judged_band/reason but cannot "
            "change the headline verdict under the current design"
        ),
    }


def main() -> int:
    dataset_path = REPO_ROOT / "evals" / "golden_dataset.json"
    raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    writing_items = [
        row for row in raw_dataset.get("writing", []) if row.get("label_validated") is True
    ]
    nonce = datetime.now(timezone.utc).strftime("%H%M%S")
    raw_runs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for item in writing_items:
        for repeat in range(1, REPEATS + 1):
            print(f"grading {item['id']} repeat {repeat}/{REPEATS}", flush=True)
            try:
                raw_runs.append(call_writing(item, repeat, nonce))
            except Exception as exc:
                errors.append(
                    {
                        "item_id": item["id"],
                        "repeat": repeat,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    selected_results = []
    for item in writing_items:
        candidates = [row for row in raw_runs if row["item_id"] == item["id"]]
        if not candidates:
            selected_results.append({"agent_error": "no successful grader repeat"})
        else:
            selected_results.append(candidates[0]["result"])

    same_arm = judge_arm(SAME_FAMILY_MODEL, writing_items, selected_results)
    independent_arm = judge_arm(INDEPENDENT_MODEL, writing_items, selected_results)
    elapsed_values = [row["elapsed_ms"] for row in raw_runs]
    cache_hits = sum(row["from_cache"] is True for row in raw_runs)
    report_fields = set(runner.ReportSchema.model_fields)
    metric_fields = set(runner.ReportMetrics.model_fields)
    speaking = runner.run_speaking_eval(raw_dataset)
    consistency_metrics = consistency(raw_runs) if raw_runs else {"per_item": {}, "domain": {}}

    validity_failures = list(errors)
    if len(raw_runs) != len(writing_items) * REPEATS:
        validity_failures.append(
            {"error": f"expected {len(writing_items) * REPEATS} successful runs, got {len(raw_runs)}"}
        )
    if cache_hits:
        validity_failures.append(
            {"error": f"{cache_hits} grader repeats were served from cache; self-consistency is invalid"}
        )
    for arm in (same_arm, independent_arm):
        if arm["accuracy"]["errored"]:
            validity_failures.append(
                {"error": f"{arm['model']} judge errored on {arm['accuracy']['errored']} items"}
            )

    report = {
        "ticket": "GOA-136",
        "phase": PHASE,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "providers": {
            "graders": {
                "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
                "models": sorted(
                    {
                        os.environ.get("WRITING_MODEL", SAME_FAMILY_MODEL),
                    }
                ),
                "real": not errors and len(raw_runs) == len(writing_items) * REPEATS,
            },
            "judge_same_family": {
                "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
                "model": SAME_FAMILY_MODEL,
                "real": same_arm["accuracy"]["errored"] == 0,
            },
            "judge_independent": {
                "base_url": os.environ.get(
                    "EVAL_JUDGE_BASE_URL", "https://agentrouter.org/v1"
                ),
                "model": INDEPENDENT_MODEL,
                "real": independent_arm["accuracy"]["errored"] == 0,
            },
        },
        "n_samples": len(raw_runs),
        "valid": not validity_failures,
        "validity_failures": validity_failures,
        "dataset_provenance": {
            "writing": provenance(raw_dataset.get("writing", [])),
            "writing_synthetic_unvalidated": provenance(
                raw_dataset.get("writing_synthetic_unvalidated", [])
            ),
            "speaking": provenance(raw_dataset.get("speaking", [])),
        },
        "current_report_surface": {
            "judge_model_recorded": "judge_model" in report_fields,
            "grader_models_recorded": "grader_models" in report_fields,
            "provenance_recorded": "provenance" in report_fields,
            "consistency_recorded": "consistency" in report_fields,
            "accuracy_caveat_recorded": "accuracy_caveat" in metric_fields,
        },
        "metrics": {
            "E1_writing": {
                "n_validated": len(writing_items),
                "same_family": same_arm,
                "independent": independent_arm,
            },
            "E2_speaking": speaking,
            "E6_E7_self_consistency": consistency_metrics,
            "E8_judge_family_delta": family_delta(same_arm, independent_arm),
            "E9_judge_cost": {
                SAME_FAMILY_MODEL: {
                    "input_tokens": same_arm["accuracy"]["input_tokens"],
                    "output_tokens": same_arm["accuracy"]["output_tokens"],
                    "cached_count": same_arm["accuracy"]["cached_count"],
                    "incremental_cost_usd": same_arm["incremental_cost_usd"],
                },
                INDEPENDENT_MODEL: {
                    "input_tokens": independent_arm["accuracy"]["input_tokens"],
                    "output_tokens": independent_arm["accuracy"]["output_tokens"],
                    "cached_count": independent_arm["accuracy"]["cached_count"],
                    "incremental_cost_usd": independent_arm["incremental_cost_usd"],
                },
            },
            "grader_latency_ms": {
                "min": round(min(elapsed_values), 3) if elapsed_values else None,
                "median": round(statistics.median(elapsed_values), 3)
                if elapsed_values
                else None,
                "p95": percentile(elapsed_values, 0.95),
                "max": round(max(elapsed_values), 3) if elapsed_values else None,
            },
            "grader_cache_hits": cache_hits,
        },
        "raw_grader_runs": raw_runs,
        "grader_errors": errors,
    }

    out_dir = REPO_ROOT / "perf" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"GOA-136-{PHASE}-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    print(json.dumps({
        "valid": report["valid"],
        "n_samples": report["n_samples"],
        "writing_accuracy": independent_arm["accuracy"]["accuracy"],
        "writing_mae": independent_arm["mae"]["overall"],
        "domain_consistency": consistency_metrics.get("domain"),
        "judge_family_delta": report["metrics"]["E8_judge_family_delta"],
        "judge_cost": report["metrics"]["E9_judge_cost"],
    }, indent=2), flush=True)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
