"""Live RAG retrieval benchmark with a verifiable corpus and validity gates.

GOA-033 introduced this harness. GOA-137 extends the same path with adversarial
subsets, Recall@5/10, nDCG@10, explicit arm configurations and a frozen-corpus
comparison. A report is never written when the corpus differs or the cross-encoder
has degraded.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from evals.frozen_corpus import corpus_digest, read_snapshot
from evals.rag_retrieval_eval import ndcg_at_k, recall_at_k, reciprocal_rank


RAG_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:8084").rstrip("/")
RAG_QUERY_URL = f"{RAG_URL}/query"
INTERNAL_API_KEY = os.environ.get(
    "INTERNAL_API_KEY", "supersecret_internal_key_123"
)
DEFAULT_DB_URL = "postgresql://goa:goa_pass@localhost:5432/rag_db"
DEFAULT_DATASET = Path("evals/golden_dataset.json")
DEFAULT_SNAPSHOT = Path("evals/corpora/GOA-137-documents.jsonl.gz")

ARM_CONFIGS: dict[str, dict[str, Any]] = {
    "baseline": {
        "rerank_enabled": False,
        "threshold_enabled": False,
        "retrieval_width": 5,
        "ivfflat_probes": 1,
        "hybrid_enabled": False,
        "category_filter": False,
    },
    "probes-only": {
        "rerank_enabled": False,
        "threshold_enabled": False,
        "retrieval_width": 5,
        "ivfflat_probes": 10,
        "hybrid_enabled": False,
        "category_filter": False,
    },
    "width-only": {
        "rerank_enabled": False,
        "threshold_enabled": False,
        "retrieval_width": 15,
        "ivfflat_probes": 1,
        "hybrid_enabled": False,
        "category_filter": False,
    },
    "rerank": {
        "rerank_enabled": True,
        "threshold_enabled": False,
        "retrieval_width": 15,
        "ivfflat_probes": 1,
        "hybrid_enabled": False,
        "category_filter": False,
    },
    "full": {
        "rerank_enabled": True,
        "threshold_enabled": True,
        "retrieval_width": 15,
        "ivfflat_probes": 10,
        "hybrid_enabled": False,
        "category_filter": False,
    },
    "hybrid": {
        "rerank_enabled": True,
        "threshold_enabled": True,
        "retrieval_width": 15,
        "ivfflat_probes": 10,
        "hybrid_enabled": True,
        "category_filter": False,
    },
    "hybrid-filtered": {
        "rerank_enabled": True,
        "threshold_enabled": True,
        "retrieval_width": 15,
        "ivfflat_probes": 10,
        "hybrid_enabled": True,
        "category_filter": True,
    },
}
PRE_ARMS = ("baseline", "probes-only", "width-only", "rerank", "full")
POST_ARMS = PRE_ARMS + ("hybrid", "hybrid-filtered")


class BenchmarkEnvironmentError(RuntimeError):
    """The environment is unverifiable, so no benchmark may be emitted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_git_sha() -> str:
    injected = os.environ.get("BENCHMARK_GIT_SHA")
    if injected:
        return injected
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown-sha"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def harness_fingerprint() -> dict[str, Any]:
    component_paths = (
        Path("evals/rag_benchmark.py"),
        Path("evals/rag_retrieval_eval.py"),
        Path("evals/frozen_corpus.py"),
    )
    components = {path.as_posix(): file_sha256(path) for path in component_paths}
    combined = hashlib.sha256(
        "".join(f"{path}:{digest}\n" for path, digest in components.items()).encode()
    ).hexdigest()
    return {"sha256": combined, "components": components}


async def _fetch_live_service_info(database_url: str) -> dict[str, Any]:
    connection = await asyncpg.connect(database_url)
    try:
        rows = await connection.fetch(
            """
            SELECT id, title, content, source_url, category
            FROM documents
            ORDER BY id
            """
        )
        live_probes = await connection.fetchval("SHOW ivfflat.probes")
        index_options = await connection.fetchval(
            """
            SELECT reloptions::text
            FROM pg_class
            WHERE relname = 'documents_embedding_idx'
            """
        )
    finally:
        await connection.close()
    document_count, content_hash = corpus_digest(dict(row) for row in rows)
    return {
        "document_count": document_count,
        "content_hash": content_hash,
        "ivfflat_probes_session_default": int(live_probes or 1),
        "index_reloptions": index_options,
    }


def fetch_live_service_info() -> dict[str, Any]:
    database_url = os.environ.get("RAG_DATABASE_URL", DEFAULT_DB_URL)
    try:
        return asyncio.run(_fetch_live_service_info(database_url))
    except Exception as exc:
        raise BenchmarkEnvironmentError(
            f"Cannot read live corpus metadata from {database_url!r}: {exc}"
        ) from exc


def fetch_gauge(metric_name: str) -> float | None:
    try:
        response = httpx.get(f"{RAG_URL}/metrics/", timeout=10.0)
        response.raise_for_status()
    except Exception as exc:
        raise BenchmarkEnvironmentError(
            f"Cannot read live RAG metrics from {RAG_URL!r}: {exc}"
        ) from exc
    prefix = f"{metric_name} "
    for line in response.text.splitlines():
        if line.startswith(prefix):
            return float(line.split()[-1])
    return None


def fetch_live_rerank_mode() -> str:
    value = fetch_gauge("goa_rag_rerank_mode")
    if value == 1.0:
        return "cross-encoder"
    if value == 0.0:
        return "DEGRADED-fallback"
    return "unknown"


def load_and_verify_corpus(snapshot_path: Path) -> dict[str, Any]:
    if not snapshot_path.exists():
        raise BenchmarkEnvironmentError(
            f"Frozen corpus snapshot does not exist: {snapshot_path}"
        )
    snapshot_count, snapshot_hash = corpus_digest(read_snapshot(snapshot_path))
    live = fetch_live_service_info()
    if (live["document_count"], live["content_hash"]) != (
        snapshot_count,
        snapshot_hash,
    ):
        raise BenchmarkEnvironmentError(
            "Live corpus differs from the committed snapshot: "
            f"live={live['document_count']}/{live['content_hash']}, "
            f"snapshot={snapshot_count}/{snapshot_hash}"
        )
    return {
        **live,
        "snapshot_path": snapshot_path.as_posix(),
        "snapshot_sha256": file_sha256(snapshot_path),
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _quality_summary(results: list[dict[str, Any]], subset: str | None) -> dict[str, Any]:
    answerable = [
        result
        for result in results
        if not result["unanswerable"]
        and (subset is None or result["subset"] == subset)
    ]
    return {
        "n": len(answerable),
        "recall_at_5": _mean([item["recall_at_5"] for item in answerable]),
        "recall_at_10": _mean([item["recall_at_10"] for item in answerable]),
        "mrr": _mean([item["mrr"] for item in answerable]),
        "ndcg_at_10": _mean([item["ndcg_at_10"] for item in answerable]),
    }


def _arm_hit_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    labelled_sources = [
        source_arm
        for result in results
        for source_arm in result["retrieval_arms"]
        if source_arm is not None
    ]
    if not labelled_sources:
        return {
            "available": False,
            "dense_only": None,
            "lexical_only": None,
            "both": None,
            "entity_lexical_contribution_rate": None,
            "reason": "The serving API did not expose candidate-arm provenance.",
        }
    counts = {"dense_only": 0, "lexical_only": 0, "both": 0}
    for arms in labelled_sources:
        key = "both" if len(arms) > 1 else f"{arms[0]}_only"
        counts[key] += 1
    entity_sources = [
        arms
        for result in results
        if result["subset"] == "entity"
        for arms in result["retrieval_arms"]
        if arms is not None
    ]
    entity_lexical = sum("lexical" in arms for arms in entity_sources)
    return {
        "available": True,
        **counts,
        "entity_lexical_contribution_rate": (
            entity_lexical / len(entity_sources) if entity_sources else None
        ),
        "reason": None,
    }


def run_arm(
    label: str,
    items: list[dict[str, Any]],
    corpus: dict[str, Any],
    *,
    dataset_path: Path = DEFAULT_DATASET,
) -> dict[str, Any]:
    if label not in ARM_CONFIGS:
        raise ValueError(f"Unknown benchmark arm: {label}")
    config = ARM_CONFIGS[label]
    live_rerank_mode = fetch_live_rerank_mode()
    if live_rerank_mode != "cross-encoder":
        raise BenchmarkEnvironmentError(
            f"RERANK_MODE validity gate failed: live mode is {live_rerank_mode!r}. "
            "Refusing to write a report."
        )

    per_question: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    with httpx.Client(timeout=45.0) as client:
        for index, item in enumerate(items, 1):
            relevant_ids = set(item.get("relevant_document_ids", []))
            unanswerable = item.get("unanswerable", not relevant_ids)
            body: dict[str, Any] = {
                "question": item["question"],
                "userId": f"bench-{label}",
                "topK": 10,
            }
            category_applied = bool(config["category_filter"] and item.get("category"))
            if category_applied:
                body["category"] = item["category"]
            headers = {
                "X-Internal-Api-Key": INTERNAL_API_KEY,
                "X-RAG-Rerank-Enabled": str(config["rerank_enabled"]).lower(),
                "X-RAG-Threshold-Enabled": str(config["threshold_enabled"]).lower(),
                "X-RAG-Retrieval-Width": str(config["retrieval_width"]),
                "X-RAG-IVFFlat-Probes": str(config["ivfflat_probes"]),
                "X-RAG-Retrieval-Only": "true",
                "X-RAG-Hybrid-Enabled": str(config["hybrid_enabled"]).lower(),
            }
            started = time.perf_counter()
            try:
                response = client.post(RAG_QUERY_URL, json=body, headers=headers)
                response.raise_for_status()
            except Exception as exc:
                raise BenchmarkEnvironmentError(
                    f"Arm {label!r} query {item.get('id', index)!r} failed: {exc}"
                ) from exc
            latency_ms = (time.perf_counter() - started) * 1000
            payload = response.json()
            sources = payload.get("sources", [])
            retrieved_ids = [
                source["id"]
                for source in sources
                if isinstance(source, dict) and "id" in source
            ]
            refused = (
                payload.get("answer") is None
                and payload.get("reason") == "insufficient_data"
            )
            arm_labels = [
                source.get("retrieval_arms")
                if isinstance(source, dict)
                else None
                for source in sources
            ]
            result = {
                "id": item.get("id"),
                "question": item["question"],
                "subset": item.get("subset", "core"),
                "unanswerable": unanswerable,
                "category_requested": item.get("category") if category_applied else None,
                "relevant_document_ids": sorted(relevant_ids),
                "retrieved_document_ids": retrieved_ids,
                "rank_of_first_relevant": next(
                    (
                        rank
                        for rank, document_id in enumerate(retrieved_ids, 1)
                        if document_id in relevant_ids
                    ),
                    None,
                ),
                "recall_at_5": recall_at_k(retrieved_ids, relevant_ids, 5),
                "recall_at_10": recall_at_k(retrieved_ids, relevant_ids, 10),
                "mrr": reciprocal_rank(retrieved_ids[:10], relevant_ids),
                "ndcg_at_10": ndcg_at_k(retrieved_ids, relevant_ids, 10),
                "refused": refused,
                "latency_ms": latency_ms,
                "retrieval_arms": arm_labels,
            }
            per_question.append(result)
            latencies_ms.append(latency_ms)
            print(
                f"[{label} {index:02d}/{len(items)}] "
                f"R@10={result['recall_at_10']:.2f} "
                f"MRR={result['mrr']:.3f} refused={refused} "
                f"{latency_ms:.1f}ms {item.get('id', '')}"
            )

    answerable = [result for result in per_question if not result["unanswerable"]]
    unanswerable = [result for result in per_question if result["unanswerable"]]
    correct_refusals = sum(result["refused"] for result in unanswerable)
    false_refusals = sum(result["refused"] for result in answerable)
    return {
        "label": label,
        "captured_at": utc_now(),
        "config": config,
        "fingerprint": {
            "git_sha": get_git_sha(),
            "dataset_path": dataset_path.as_posix(),
            "dataset_sha256": file_sha256(dataset_path),
            "corpus_document_count": corpus["document_count"],
            "corpus_content_hash": corpus["content_hash"],
            "snapshot_path": corpus["snapshot_path"],
            "snapshot_sha256": corpus["snapshot_sha256"],
            "index_reloptions": corpus["index_reloptions"],
            "ivfflat_probes_session_default": corpus[
                "ivfflat_probes_session_default"
            ],
            "embedding_model": "nomic-embed-text",
            "rerank_mode_live": live_rerank_mode,
            "rerank_degraded": False,
            "retrieval_only": True,
            "latency_measures": "retrieval_plus_rerank_no_llm",
        },
        "quality": {
            "all": _quality_summary(per_question, None),
            "entity": _quality_summary(per_question, "entity"),
            "numeric": _quality_summary(per_question, "numeric"),
        },
        "refusal": {
            "n_answerable": len(answerable),
            "n_unanswerable": len(unanswerable),
            "correct_refusals": correct_refusals,
            "false_refusals": false_refusals,
            "unanswerable_refusal_rate": (
                correct_refusals / len(unanswerable) if unanswerable else None
            ),
            "false_refusal_rate": (
                false_refusals / len(answerable) if answerable else None
            ),
        },
        "latency_ms": {
            "n": len(latencies_ms),
            "p50": _percentile(latencies_ms, 0.50),
            "p95": _percentile(latencies_ms, 0.95),
        },
        "retrieval_arm_hits": _arm_hit_summary(per_question),
        "per_question": per_question,
    }


def load_items(dataset_path: Path) -> list[dict[str, Any]]:
    with dataset_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    items = data.get("rag_retrieval", [])
    if not items:
        raise BenchmarkEnvironmentError("Dataset has no rag_retrieval items")
    for subset in ("entity", "numeric"):
        subset_items = [item for item in items if item.get("subset") == subset]
        if len(subset_items) != 10:
            raise BenchmarkEnvironmentError(
                f"Subset {subset!r} must contain exactly 10 items; found {len(subset_items)}"
            )
        if any(not item.get("relevant_document_ids") for item in subset_items):
            raise BenchmarkEnvironmentError(
                f"Subset {subset!r} contains an item without hand-labelled document ids"
            )
    return items


def run_matrix(
    phase: str,
    output_dir: Path,
    *,
    dataset_path: Path = DEFAULT_DATASET,
    snapshot_path: Path = DEFAULT_SNAPSHOT,
) -> Path:
    items = load_items(dataset_path)
    corpus = load_and_verify_corpus(snapshot_path)
    rerank_mode = fetch_live_rerank_mode()
    if rerank_mode != "cross-encoder":
        raise BenchmarkEnvironmentError(
            f"RERANK_MODE validity gate failed before matrix: {rerank_mode!r}"
        )
    arms = PRE_ARMS if phase == "pre" else POST_ARMS
    results = {
        arm: run_arm(arm, items, corpus, dataset_path=dataset_path) for arm in arms
    }
    subset_counts = {
        "dataset": len(items),
        "answerable": sum(not item.get("unanswerable", False) for item in items),
        "unanswerable": sum(item.get("unanswerable", False) for item in items),
        "entity": sum(item.get("subset") == "entity" for item in items),
        "numeric": sum(item.get("subset") == "numeric" for item in items),
    }
    artifact = {
        "schema_version": "goa.rag-retrieval-benchmark.v2",
        "ticket": "GOA-137",
        "phase": phase,
        "captured_at": utc_now(),
        "valid": True,
        "validity": {
            "live_corpus_matches_snapshot": True,
            "rerank_degraded": False,
            "rerank_mode_live": rerank_mode,
            "retrieval_only": True,
        },
        "harness": harness_fingerprint(),
        "corpus": corpus,
        "dataset": {
            "path": dataset_path.as_posix(),
            "sha256": file_sha256(dataset_path),
            **subset_counts,
            "adversarial_label_method": "manual inspection of frozen corpus",
        },
        "arms": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"GOA-137-{phase}-{stamp}.json"
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(artifact, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"Saved valid GOA-137 {phase.upper()} matrix: {output_path}")
    return output_path


def run_single(label: str, output_dir: Path) -> Path:
    items = load_items(DEFAULT_DATASET)
    corpus = load_and_verify_corpus(DEFAULT_SNAPSHOT)
    result = run_arm(label, items, corpus)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{label}.json"
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--matrix", choices=("pre", "post"))
    selection.add_argument("--label", choices=tuple(ARM_CONFIGS))
    parser.add_argument("--out", type=Path, default=Path("evals/benchmarks"))
    args = parser.parse_args()
    try:
        if args.matrix:
            run_matrix(args.matrix, args.out)
        else:
            run_single(args.label, args.out)
    except BenchmarkEnvironmentError as exc:
        print(f"BENCHMARK ABORTED — environment not verifiable:\n  {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
