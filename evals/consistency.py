"""Repeat grader calls and publish self-agreement without hiding missing data."""

from __future__ import annotations

import base64
import statistics
from datetime import datetime, timezone
from typing import Any, Callable


def summarise_values(values: list[float]) -> dict[str, Any]:
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


def summarise_runs(rows: list[dict[str, Any]], repeats: int) -> dict[str, Any]:
    per_item: dict[str, Any] = {}
    for item_id in sorted({row["item_id"] for row in rows}):
        item_rows = [row for row in rows if row["item_id"] == item_id]
        bands = [float(row["result"]["overall_band"]) for row in item_rows]
        criterion_names = sorted(
            {
                name
                for row in item_rows
                for name in (row["result"].get("criteria") or {})
            }
        )
        criteria = {}
        for name in criterion_names:
            values = [
                float(row["result"]["criteria"][name])
                for row in item_rows
                if row["result"].get("criteria", {}).get(name) is not None
            ]
            criteria[name] = summarise_values(values)
        per_item[item_id] = {
            **summarise_values(bands),
            "unanimous": len(bands) == repeats and len(set(bands)) == 1,
            "criteria": criteria,
        }

    item_stats = list(per_item.values())
    complete = [row for row in item_stats if row["n"] == repeats]
    all_bands = [
        float(row["result"]["overall_band"])
        for row in rows
    ]
    domain: dict[str, Any] = {
        "n_items": len(item_stats),
        "n_complete_items": len(complete),
        "repeats": repeats,
        "mean": round(statistics.mean(all_bands), 4) if all_bands else None,
        "std_dev": round(
            statistics.mean(row["std_dev"] for row in item_stats), 4
        )
        if item_stats
        else None,
        "std_dev_definition": "mean of per-item population standard deviations",
        "max_spread": max(
            (row["max_spread"] for row in item_stats), default=None
        ),
        "modal_band": statistics.multimode(
            [row["modal_band"] for row in item_stats]
        )[0]
        if item_stats
        else None,
        "unanimous_rate": round(
            sum(row["unanimous"] for row in complete) / len(complete), 4
        )
        if complete
        else None,
    }
    criterion_names = sorted(
        {name for row in item_stats for name in row["criteria"]}
    )
    domain["criteria"] = {}
    for name in criterion_names:
        available = [
            row["criteria"][name]
            for row in item_stats
            if name in row["criteria"]
        ]
        domain["criteria"][name] = {
            "std_dev": round(
                statistics.mean(row["std_dev"] for row in available), 4
            ),
            "std_dev_definition": "mean of per-item population standard deviations",
            "max_spread": max(row["max_spread"] for row in available),
            "modal_band": statistics.multimode(
                [row["modal_band"] for row in available]
            )[0],
            "unanimous_rate": round(
                sum(row["max_spread"] == 0 for row in available)
                / len(available),
                4,
            ),
        }
    return {"per_item": per_item, "domain": domain}


def read_cost_telemetry(user_id: str, model: str) -> dict[str, Any]:
    """Read the same Redis token counters priced by GOA-135.

    A missing key is unknown, not a zero-cost run.
    """
    try:
        import os
        import redis
        from goa_pricing import cost_usd

        encoded_model = base64.urlsafe_b64encode(model.encode("utf-8")).decode(
            "ascii"
        ).rstrip("=")
        date = datetime.now(timezone.utc).date().isoformat()
        key = (
            f"llm:tokens:{date}:user:{user_id}:writing:model:{encoded_model}"
        )
        client = redis.from_url(
            os.environ.get(
                "REDIS_GATEWAY_URL", "redis://redis-gateway:6379/0"
            ),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        counters = client.hgetall(key)
        if not counters:
            return {
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
                "reason": f"no telemetry found for {key}",
            }
        input_tokens = int(counters.get("input", 0))
        output_tokens = int(counters.get("output", 0))
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd(model, input_tokens, output_tokens),
            "reason": None,
            "source": "GOA-135 Redis token telemetry and shared pricing table",
        }
    except Exception as exc:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
            "reason": f"cost telemetry unavailable: {type(exc).__name__}: {exc}",
        }


def run_consistency(
    items: list[dict[str, Any]],
    evaluator: Callable[[dict[str, Any], int, str], dict[str, Any]],
    *,
    repeats: int = 5,
    user_id: str,
    model: str,
    telemetry_reader: Callable[[str, str], dict[str, Any]] = read_cost_telemetry,
) -> dict[str, Any]:
    if repeats < 2:
        raise ValueError("consistency requires at least two repeats")

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in items:
        for repeat in range(1, repeats + 1):
            try:
                result = evaluator(item, repeat, user_id)
                if result.get("overall_band") is None:
                    raise ValueError("grader response did not contain overall_band")
                if result.get("from_cache") is True:
                    raise ValueError("grader repeat was served from cache")
                rows.append(
                    {
                        "item_id": item.get("id", "<unknown>"),
                        "repeat": repeat,
                        "result": result,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "item_id": item.get("id", "<unknown>"),
                        "repeat": repeat,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    expected_calls = len(items) * repeats
    return {
        **summarise_runs(rows, repeats),
        "n_calls": len(rows),
        "expected_calls": expected_calls,
        "valid": len(rows) == expected_calls and not errors,
        "errors": errors,
        "cost": telemetry_reader(user_id, model),
    }
