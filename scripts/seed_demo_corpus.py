#!/usr/bin/env python3
"""Fill the demo corpus with real, resumable MastersPortal Tier-1 records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

for candidate in (
    Path(__file__).resolve().parents[1] / "services" / "ingestion",
    Path("/app"),
):
    if candidate.exists():
        sys.path.insert(0, str(candidate))

from client import get_document_stats
from app.adapters.masters_portal import DISCIPLINE_IDS
from app.core.crawl_state import CrawlStateManager
from handler import handle_ingestion


def masters_catalog_exhausted() -> bool:
    """Read the ingestion-owned cursors; this never queries another service DB."""
    state = CrawlStateManager(read_only=True)
    return all(
        bool(state.get_cursor("masters_portal", discipline)["exhausted"])
        for discipline in DISCIPLINE_IDS
    )


def fill_corpus(
    target: int,
    max_runs: int,
    minimum: int | None = None,
    *,
    stats_reader: Callable[[], dict] = get_document_stats,
    runner: Callable[[dict], dict] = handle_ingestion,
    exhausted_reader: Callable[[], bool] = masters_catalog_exhausted,
) -> dict:
    minimum = target if minimum is None else minimum
    if target < 1 or minimum < 1 or minimum > target or max_runs < 1:
        raise ValueError("minimum, target and max_runs must be positive; minimum <= target")

    before = stats_reader()
    current = int(before["total"])
    runs = 0
    last_summary = None
    # The demo floor is a readiness gate, not a mandate to hammer an upstream
    # source until an aspirational round number is reached.  Once the real,
    # deduplicated corpus is inside the accepted range, preflight must be fast and
    # network-independent. Explicit ingestion jobs can still continue toward target.
    if current >= minimum:
        catalog_exhausted = exhausted_reader()
        return {
            "status": "ready",
            "target": target,
            "minimum": minimum,
            "catalog_exhausted": catalog_exhausted,
            "ready_reason": "target_reached" if current >= target else "minimum_reached",
            "runs": 0,
            "before": before,
            "after": before,
            "last_ingestion_summary": None,
        }

    while current < target and runs < max_runs:
        runs += 1
        last_summary = runner(
            {
                "adapters": ["masters_portal"],
                "tier": 1,
                "max_items": 2_000,
                "max_seconds": 3_600,
            }
        )
        stats = stats_reader()
        next_total = int(stats["total"])
        print(
            f"corpus run {runs}/{max_runs}: {current} -> {next_total} documents",
            file=sys.stderr,
            flush=True,
        )
        current = next_total
        sources = last_summary.get("sources", [])
        if sources and all(int(source.get("remaining", 0)) == 0 for source in sources):
            break

    final = stats_reader()
    final_total = int(final["total"])
    catalog_exhausted = bool(
        last_summary
        and last_summary.get("sources")
        and all(int(source.get("remaining", 0)) == 0 for source in last_summary["sources"])
    )
    ready = final_total >= target or (catalog_exhausted and final_total >= minimum)
    result = {
        "status": "ready" if ready else "not_ready",
        "target": target,
        "minimum": minimum,
        "catalog_exhausted": catalog_exhausted,
        "ready_reason": (
            "target_reached" if final_total >= target else "catalog_exhausted"
        ) if ready else None,
        "runs": runs,
        "before": before,
        "after": final,
        "last_ingestion_summary": last_summary,
    }
    if not ready:
        raise RuntimeError(
            f"real ingestion stopped at {final['total']} documents; target is {target}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=10_000)
    parser.add_argument("--minimum", type=int, default=7_500)
    parser.add_argument("--max-runs", type=int, default=400)
    args = parser.parse_args()
    try:
        print(json.dumps(fill_corpus(args.target, args.max_runs, args.minimum), indent=2, default=str))
        return 0
    except Exception as error:
        print(f"DEMO CORPUS NOT READY: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
