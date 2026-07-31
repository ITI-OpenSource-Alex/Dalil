"""
evals/rag_benchmark.py

Section 4B Benchmarking Harness for GOA RAG Quality.
Emits committed benchmark JSON artifacts under evals/benchmarks/ with live environment fingerprinting.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
import httpx
from evals.rag_retrieval_eval import recall_at_15, reciprocal_rank, relevant_at_1

RAG_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:8084")

# Set from --allow-degraded. Defaults to False so an unattended run cannot silently
# mint an artifact for a cross-encoder that never loaded.
ALLOW_DEGRADED = False

# Measure retrieval without generating an answer. Default True: this harness exists to
# measure ranking, and coupling it to LLM availability is how an outage gets recorded as
# a quality regression. Set --with-generation for an end-to-end latency figure.
RETRIEVAL_ONLY = True

RAG_QUERY_URL = "http://localhost:8084/query"
INTERNAL_API_KEY = "supersecret_internal_key_123"


def get_git_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
        return out.strip()
    except Exception:
        return "unknown-sha"


class BenchmarkEnvironmentError(RuntimeError):
    """The environment could not be read, so the artifact cannot be trusted."""


# Same default the RAG service uses. Override with RAG_DATABASE_URL when running the
# harness from outside the compose network.
DEFAULT_DB_URL = "postgresql://goa:goa_pass@localhost:5432/rag_db"


def fetch_live_service_info():
    """Read corpus size, checksum and ivfflat.probes from the live database.

    This function used to connect to postgres:postgres@localhost/goa_rag -- credentials
    and a database name that do not exist in this project. It therefore raised on every
    invocation and the `except` returned hardcoded values (2905 rows, a literal string
    where the checksum should be, probes=1). Those values were then written into the
    artifact as though they had been measured.

    That is worse than an obviously fake fingerprint, because it looks real. A benchmark
    whose provenance block is invented is not evidence of anything, so this now raises
    instead of guessing. An artifact is either measured or it is not written.
    """
    import asyncio

    import asyncpg

    db_url = os.environ.get("RAG_DATABASE_URL", DEFAULT_DB_URL)

    async def query_db_meta():
        conn = await asyncpg.connect(db_url)
        try:
            count = await conn.fetchval("SELECT count(*) FROM documents;")
            ids_rows = await conn.fetch("SELECT id FROM documents ORDER BY id;")
            csum = hashlib.sha256(
                "".join(str(r["id"]) for r in ids_rows).encode("utf-8")
            ).hexdigest()[:16]
            # SHOW returns '' outside a transaction that set it; treat that as the
            # pgvector default rather than crashing on int('').
            raw_probes = await conn.fetchval("SHOW ivfflat.probes;")
            lists = await conn.fetchval(
                "SELECT reloptions::text FROM pg_class WHERE relname = 'documents_embedding_idx';"
            )
            return count, csum, int(raw_probes) if raw_probes else 1, lists
        finally:
            await conn.close()

    try:
        return asyncio.run(query_db_meta())
    except Exception as exc:
        raise BenchmarkEnvironmentError(
            f"Cannot read corpus metadata from {db_url!r}: {exc}. "
            "Refusing to emit an artifact with an unverified fingerprint. "
            "Set RAG_DATABASE_URL if the database is not reachable at the default."
        ) from exc


def fetch_live_rerank_mode(base_url: str) -> str:
    """Ask the running service which re-ranker is ACTUALLY serving.

    The cross-encoder degrades to a token-overlap heuristic when the model cannot
    load. Recording the *configured* flag rather than the *live* mode produces an
    artifact claiming `rerank_enabled: true` for a run that never touched the
    cross-encoder. Read goa_rag_rerank_mode from /metrics instead.
    """
    try:
        import httpx

        # follow_redirects is required: the app serves /metrics as a 307 to /metrics/,
        # and httpx does not follow by default -- the probe would read an empty body,
        # report "unknown", and block every rerank run for the wrong reason.
        body = httpx.get(f"{base_url}/metrics", timeout=10.0, follow_redirects=True).text
        for line in body.splitlines():
            if line.startswith("goa_rag_rerank_mode "):
                return "cross-encoder" if float(line.split()[1]) == 1.0 else "DEGRADED-fallback"
    except Exception:
        pass
    return "unknown"


def run_benchmark(label: str, out_dir: str = "evals/benchmarks"):
    os.makedirs(out_dir, exist_ok=True)
    dataset_path = "evals/golden_dataset.json"

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("rag_retrieval", [])
    if not items:
        items = [i for i in data.get("rag", []) if "relevant_document_ids" in i]

    # Matrix Run Configuration Flags
    rerank_enabled = "rerank" in label or "full" in label
    threshold_enabled = "full" in label or "threshold" in label
    retrieval_width = 15 if ("width" in label or "rerank" in label or "full" in label) else 5
    effective_probes = 10 if ("probes" in label or "full" in label) else 1

    git_sha = get_git_sha()
    corpus_rows, corpus_checksum, live_probes, index_opts = fetch_live_service_info()
    live_rerank_mode = fetch_live_rerank_mode(RAG_URL)

    # The artifact must describe the run that happened, not the run that was intended.
    # If the service is serving the degraded token-overlap fallback, a row labelled
    # "rerank" measures the fallback -- so refuse to mint an artifact that would claim
    # otherwise. Pass --allow-degraded to capture it deliberately, clearly marked.
    if rerank_enabled and live_rerank_mode != "cross-encoder" and not ALLOW_DEGRADED:
        raise BenchmarkEnvironmentError(
            f"Run '{label}' enables re-ranking but the live service reports "
            f"rerank mode = {live_rerank_mode!r}. The cross-encoder is not serving, so "
            "this run would measure the token-overlap fallback while the artifact claimed "
            "otherwise. Rebuild the RAG image (see services/rag/Dockerfile) or pass "
            "--allow-degraded to record it as a deliberately degraded run."
        )

    r1_scores, rec15_scores, mrr_scores = [], [], []

    per_question_results = []
    latencies_ms = []

    n_answerable = 0
    n_unanswerable = 0
    correct_refusals = 0
    false_refusals = 0

    print(f"\n========================================================")
    print(f" BENCHMARK RUN: [{label.upper()}] ({len(items)} queries)")
    print(f"   Fingerprint: SHA={git_sha[:7]} | Rows={corpus_rows} | Checksum={corpus_checksum}")
    print(f"   Flags: rerank={rerank_enabled} | threshold={threshold_enabled} | width={retrieval_width} | probes={effective_probes}")
    print(f"========================================================\n")

    with httpx.Client(timeout=35.0) as client:
        for idx, item in enumerate(items, 1):
            q = item["question"]
            rel_ids = set(item.get("relevant_document_ids", []))
            # Prefer the explicit dataset flag; fall back to "no ground-truth ids" for
            # older items that predate it.
            is_unanswerable = item.get("unanswerable", len(rel_ids) == 0)

            if is_unanswerable:
                n_unanswerable += 1
            else:
                n_answerable += 1

            t0 = time.time()
            headers = {
                "X-Internal-Api-Key": INTERNAL_API_KEY,
                "X-RAG-Rerank-Enabled": "true" if rerank_enabled else "false",
                "X-RAG-Threshold-Enabled": "true" if threshold_enabled else "false",
                "X-RAG-Retrieval-Width": str(retrieval_width),
                "X-RAG-IVFFlat-Probes": str(effective_probes),
                # Retrieval metrics are computed from `sources`, which are final before
                # generation. Asking for the answer too would make this benchmark fail
                # whenever the LLM is unavailable and record it as a quality collapse.
                # Latency here is therefore RETRIEVAL latency, not end-to-end -- the
                # artifact records which, so the two are never compared by mistake.
                "X-RAG-Retrieval-Only": "true" if RETRIEVAL_ONLY else "false",
            }
            try:
                resp = client.post(
                    RAG_QUERY_URL,
                    json={"question": q, "userId": f"bench-{label}"},
                    headers=headers
                )
                resp.raise_for_status()
                res_data = resp.json()

            except Exception as exc:
                print(f"[FATAL] Query failed for '{q}': {exc}")
                sys.exit(1)
            dur_ms = (time.time() - t0) * 1000
            latencies_ms.append(dur_ms)

            is_refused = res_data.get("answer") is None and res_data.get("reason") == "insufficient_data"

            if is_unanswerable:
                if is_refused:
                    correct_refusals += 1
            else:
                if is_refused:
                    false_refusals += 1

            sources = res_data.get("sources", [])
            ret_ids = [s["id"] for s in sources if isinstance(s, dict) and "id" in s]

            r1 = relevant_at_1(ret_ids, rel_ids)
            rec15 = recall_at_15(ret_ids, rel_ids)
            rr = reciprocal_rank(ret_ids, rel_ids)

            # Retrieval quality is only defined where a relevant document exists. An
            # unanswerable question has none, so it would score 0 on all three and drag
            # the averages down in proportion to how many negatives the dataset holds --
            # adding negatives would read as a quality regression. Negatives are scored
            # by the refusal counters below instead.
            if not is_unanswerable:
                r1_scores.append(r1)
                rec15_scores.append(rec15)
                mrr_scores.append(rr)

            rank_of_rel = next((i + 1 for i, did in enumerate(ret_ids) if did in rel_ids), None)
            per_question_results.append({
                "question": q,
                "rank_of_relevant": rank_of_rel,
                "mrr": rr,
                "relevant_at_1": r1,
                "recall_at_15": rec15,
                "refused": is_refused
            })

            print(f"[{idx:2d}/{len(items)}] MRR={rr:.3f} | rel@1={r1:.2f} | rec@15={rec15:.2f} | refused={is_refused} | {dur_ms:.1f}ms | '{q[:35]}...'")

    avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0
    avg_r1 = sum(r1_scores) / len(r1_scores) if r1_scores else 0.0
    avg_rec15 = sum(rec15_scores) / len(rec15_scores) if rec15_scores else 0.0

    sorted_lats = sorted(latencies_ms)
    p50 = sorted_lats[int(len(sorted_lats) * 0.50)] if sorted_lats else 0.0
    p95 = sorted_lats[int(len(sorted_lats) * 0.95)] if sorted_lats else 0.0

    artifact = {
        "label": label,
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "fingerprint": {
            # Measured from the environment. Anything that could not be read raises
            # rather than falling back to a plausible-looking literal.
            "git_sha": git_sha,
            "corpus_rows": corpus_rows,
            "corpus_checksum": corpus_checksum,
            "index_reloptions": index_opts,
            "ivfflat_probes_requested": effective_probes,
            "ivfflat_probes_session_default": live_probes,
            "embedding_model": "nomic-embed-text",
            "llm_model": "claude-opus-4-8",
            "retrieval_width": retrieval_width,
            "return_width": 5,
            "rerank_requested": rerank_enabled,
            # What the service was ACTUALLY serving, read from /metrics -- not the
            # flag we asked for. These disagree whenever the model fails to load.
            "rerank_mode_live": live_rerank_mode,
            "threshold_enabled": threshold_enabled,
            "cache_enabled": False,
            "retrieval_only": RETRIEVAL_ONLY,
            "latency_measures": "retrieval" if RETRIEVAL_ONLY else "end_to_end",
            "confidence_threshold": 0.60,
            "degraded_run": rerank_enabled and live_rerank_mode != "cross-encoder",
        },
        "quality": {
            # n is the answerable subset these metrics were computed over, not the
            # dataset size. Reporting the dataset size here would overstate the
            # denominator behind every quality figure.
            "n": len(mrr_scores),
            "n_dataset": len(items),
            "mrr": avg_mrr,
            "relevant_at_1": avg_r1,
            # Named for the width actually retrieved. Calling it recall@15 on a run
            # that retrieved 5 candidates describes a measurement that did not happen.
            f"recall_at_{retrieval_width}": avg_rec15,
            "per_question": per_question_results
        },
        "refusal": {
            "n_answerable": n_answerable,
            "n_unanswerable": n_unanswerable,
            "correct_refusals": correct_refusals,
            "false_refusals": false_refusals
        },
        "latency_ms": {
            "n": len(latencies_ms),
            "p50": p50,
            "p95": p95
        }
    }

    out_file = os.path.join(out_dir, f"{label}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print(f"\n========================================================")
    print(f" BENCHMARK SUMMARY [{label.upper()}]")
    print(f"   MRR:         {avg_mrr:.4f}")
    print(f"   relevant@1:  {avg_r1 * 100:.2f}%")
    print(f"   recall@15:   {avg_rec15 * 100:.2f}%")
    print(f"   Correct Refusals: {correct_refusals}/{n_unanswerable}")
    print(f"   False Refusals:   {false_refusals}/{n_answerable}")
    print(f"   p50 Latency: {p50:.1f} ms | p95: {p95:.1f} ms")
    print(f" Saved artifact: {out_file}")
    print(f"========================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="baseline", help="Benchmark label")
    parser.add_argument("--out", default="evals/benchmarks", help="Output directory")
    parser.add_argument(
        "--with-generation",
        action="store_true",
        help="Also generate answers. Makes latency end-to-end, and makes the run depend "
             "on LLM availability.",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="Capture a run even when the cross-encoder is not serving. The artifact "
             "is marked degraded_run=true. Do not use these numbers as a re-ranking result.",
    )
    args = parser.parse_args()
    ALLOW_DEGRADED = args.allow_degraded
    RETRIEVAL_ONLY = not args.with_generation
    try:
        run_benchmark(args.label, args.out)
    except BenchmarkEnvironmentError as exc:
        # Exit 2, distinct from a quality regression, so CI and a human can tell
        # "the environment was wrong" from "the numbers got worse".
        print(f"\nBENCHMARK ABORTED -- environment not verifiable:\n  {exc}\n")
        sys.exit(2)
