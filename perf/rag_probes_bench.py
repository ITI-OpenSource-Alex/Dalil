"""GOA-030 — ANN recall and latency as a function of ivfflat.probes.

Why this exists
---------------
GOA-030's Journey 2 requires a student-visa answer to cite the official
government or embassy URL that was actually fetched. Against the live catalogue
it cited nothing of the sort: a Germany student-visa question returned four
MastersPortal programme pages and zero visa documents, even though the correct
EU-immigration-portal chunk scores 0.854 -- the highest similarity in the whole
corpus.

The cause is not the data and not the embedding. `documents` carries an IVFFlat
index built with lists=100, and `rag_ivfflat_probes` defaults to 1, so every
production query scans one cluster in a hundred. With 3903 university chunks
against 19 visa chunks, the visa cluster is simply never probed.

GOA-137 fixed the *mechanism* (SET LOCAL is transaction-scoped and was being
discarded outside a transaction) and measured dense Recall@10 = 1.00 on the
frozen eval corpus, concluding no gain was available. That measurement is
correct and does not generalise: the frozen corpus is small enough that one
cluster covers it, so it cannot express this failure. This harness measures the
same quantity against the *live* catalogue, where it can.

What it measures
----------------
For each probes setting, over a fixed question set with known-correct source
hosts:

  recall@k   fraction of questions whose expected host appears in the top-k
  hit_rank   rank of the first correct source (None when absent, never 0)
  latency    per-query wall clock at the RAG service boundary, p50/p95

Retrieval-only mode (X-RAG-Retrieval-Only) is used deliberately: retrieval
quality exists before the LLM is called, and a recall benchmark must not be
able to fail because a provider is down.

Usage
-----
    python perf/rag_probes_bench.py --out perf/reports/GOA-030-probes-pre.json
    python perf/rag_probes_bench.py --probes 10 --out ...-post.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone

import httpx

RAG_URL = "http://localhost:8084"
USER_ID = "00000000-0000-0000-0000-000000000001"

# Each case names the host that MUST appear for the answer to be groundable.
# Hosts, not full URLs: the ingestion run that produced these rows is free to
# re-chunk, and pinning a chunk id would make this benchmark fail on a
# re-ingest for reasons unrelated to recall.
CASES = [
    ("What are the student visa requirements for Germany?", "home-affairs.ec.europa.eu"),
    ("How much money do I need in a blocked account for a German student visa?", "www.fintiba.com"),
    ("What do I need for a student visa in France?", "home-affairs.ec.europa.eu"),
    ("Tell me about the student residence permit for the Netherlands.", "home-affairs.ec.europa.eu"),
    ("What are the visa requirements to study in Italy?", "home-affairs.ec.europa.eu"),
    ("How do I get a student visa for Romania?", "studyinromania.gov.ro"),
    ("What is required for an Austrian student residence permit?", "home-affairs.ec.europa.eu"),
    ("Student visa requirements for Ireland?", "home-affairs.ec.europa.eu"),
    # Controls: programme questions must keep working. A probes change that
    # fixed visa recall by breaking programme recall would be a regression
    # this benchmark has to be able to see.
    ("Which universities in Germany offer a master's in software engineering?", "www.mastersportal.com"),
    ("Show me computer science master's programmes.", "www.mastersportal.com"),
]


def host_of(url: str | None) -> str:
    if not url:
        return ""
    return url.split("://", 1)[-1].split("/", 1)[0]


def run_case(client: httpx.Client, question: str, probes: int, top_k: int) -> dict:
    headers = {"X-RAG-Retrieval-Only": "true"}
    if probes is not None:
        headers["X-RAG-IVFFlat-Probes"] = str(probes)
    start = time.perf_counter()
    resp = client.post(
        f"{RAG_URL}/query",
        json={"question": question, "userId": USER_ID, "topK": top_k},
        headers=headers,
        timeout=120,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    sources = resp.json().get("sources", [])
    hosts = [host_of(s.get("url") or s.get("source_url")) for s in sources]
    return {"hosts": hosts, "latency_ms": elapsed_ms}


def bench(probes_values: list[int], top_k: int, repeats: int) -> dict:
    results = {}
    with httpx.Client() as client:
        for probes in probes_values:
            per_case = []
            latencies = []
            for question, expected_host in CASES:
                # Repeats guard against a single cold-cache outlier setting the
                # latency figure; recall is deterministic, so the first run
                # decides it.
                hosts = []
                for i in range(repeats):
                    out = run_case(client, question, probes, top_k)
                    latencies.append(out["latency_ms"])
                    if i == 0:
                        hosts = out["hosts"]
                rank = next(
                    (i + 1 for i, h in enumerate(hosts) if h == expected_host), None
                )
                per_case.append(
                    {
                        "question": question,
                        "expected_host": expected_host,
                        # None, never 0: "not retrieved" and "retrieved first"
                        # must not collapse into the same number.
                        "hit_rank": rank,
                        "hit": rank is not None,
                        "top_hosts": hosts[:5],
                    }
                )
            hits = [c for c in per_case if c["hit"]]
            visa_cases = [c for c in per_case if "mastersportal" not in c["expected_host"]]
            prog_cases = [c for c in per_case if "mastersportal" in c["expected_host"]]
            results[str(probes)] = {
                "recall_at_k": len(hits) / len(per_case),
                "visa_recall_at_k": sum(c["hit"] for c in visa_cases) / len(visa_cases),
                "programme_recall_at_k": sum(c["hit"] for c in prog_cases) / len(prog_cases),
                "mean_hit_rank": (
                    statistics.mean([c["hit_rank"] for c in hits]) if hits else None
                ),
                "latency_p50_ms": round(statistics.median(latencies), 1),
                "latency_p95_ms": round(
                    sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1
                ),
                "latency_mean_ms": round(statistics.mean(latencies), 1),
                "cases": per_case,
            }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--probes",
        default="1,5,10,20,50",
        help="comma-separated probes settings to sweep",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    probes_values = [int(p) for p in args.probes.split(",")]
    results = bench(probes_values, args.top_k, args.repeats)

    artefact = {
        "benchmark": "GOA-030 ivfflat probes recall/latency",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validity": {
            "corpus": "live rag_db catalogue, not the frozen eval corpus",
            "retrieval_only": True,
            "note": (
                "Recall is measured against expected source HOST, not chunk id, "
                "so a re-ingest does not invalidate it. Latency is the RAG "
                "service HTTP boundary on one developer machine and is a "
                "relative comparison between probes settings, not an SLO."
            ),
        },
        "top_k": args.top_k,
        "repeats": args.repeats,
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(artefact, handle, indent=2)

    print(f"wrote {args.out}\n")
    header = f"{'probes':>7} {'recall@k':>9} {'visa':>6} {'prog':>6} {'p50 ms':>8} {'p95 ms':>8}"
    print(header)
    print("-" * len(header))
    for probes, r in results.items():
        print(
            f"{probes:>7} {r['recall_at_k']:>9.2f} {r['visa_recall_at_k']:>6.2f} "
            f"{r['programme_recall_at_k']:>6.2f} {r['latency_p50_ms']:>8.1f} "
            f"{r['latency_p95_ms']:>8.1f}"
        )


if __name__ == "__main__":
    main()
