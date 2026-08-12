#!/usr/bin/env python3
"""Compile GOA-040 from committed, machine-readable evidence.

This intentionally reports unmet gates as failures.  It never rounds an exact
80% to "above 80%", treats a missing value as zero, or calls an old successful
load run the latest run.
"""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
DOCS = WORKSPACE_ROOT / "Docs"
EVIDENCE = DOCS / "gold-tier-evidence"
RAG_REPORT = ROOT / "evals" / "benchmarks" / "hybrid.json"
WRITING_REPORT = ROOT / "evals" / "reports" / "2026-08-07T233037.465818Z.json"
WRITING_HTML = WRITING_REPORT.with_suffix(".html")
SPEAKING_MANIFEST = ROOT / "evals" / "speaking" / "manifest" / "manifest.json"
SPEAKING_SCORES = ROOT / "evals" / "speaking" / "scores_official"
LOAD_AUTHORITATIVE = ROOT / "perf" / "reports" / "20260811T032552Z-k6.json"
LOAD_LATEST = ROOT / "perf" / "reports" / "20260811T112502Z-k6.json"
LANGFUSE = ROOT / "docs" / "evidence" / "GOA-027-langfuse-post-fix.json"


AGENTS = (
    (1, "Supervisor router", "Orchestration", "Classifies intent, resolves conversational references, and selects the downstream handoff."),
    (2, "RAG answer generator", "RAG", "Retrieves, reranks, applies confidence policy, and generates a cited answer."),
    (3, "Writing task-response examiner", "Writing", "Scores task fulfilment and development against the public IELTS descriptor."),
    (4, "Writing cohesion examiner", "Writing", "Scores organisation, progression, paragraphing, and cohesive devices."),
    (5, "Writing vocabulary examiner", "Writing", "Scores range, precision, collocation, spelling, and word formation."),
    (6, "Writing grammar examiner", "Writing", "Scores grammatical range, accuracy, punctuation, and clarity impact."),
    (7, "Speaking interviewer", "Speaking", "Controls the three-part interview and follow-up policy."),
    (8, "Speaking fluency/coherence examiner", "Speaking", "Scores coherence and, where measured audio exists, delivery fluency."),
    (9, "Speaking lexical-resource examiner", "Speaking", "Scores vocabulary range, flexibility, precision, and paraphrase."),
    (10, "Speaking grammatical-range examiner", "Speaking", "Scores structure range, flexibility, and accuracy."),
    (11, "Speaking pronunciation examiner", "Speaking", "Scores pronunciation only when acoustic evidence exists; otherwise abstains."),
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value * 100:.1f}%"


def strict_gate(value: float | None, threshold: float = 0.8) -> bool:
    return value is not None and value > threshold


def speaking_rows(
    manifest: dict[str, Any], score_dir: Path
) -> tuple[list[dict[str, Any]], float | None]:
    labels = {
        item["item_id"]: item
        for item in manifest["items"]
        if item.get("labels", {}).get("validated") is True
    }
    rows: list[dict[str, Any]] = []
    for path in sorted(score_dir.glob("*.json")):
        payload = read_json(path)
        evaluation = payload["evaluation"]
        item_id = evaluation["evaluation_id"]
        expected = labels.get(item_id, {}).get("labels", {}).get("overall_band")
        actual = evaluation.get("overall", {}).get("band")
        scored_criteria = sum(
            criterion.get("status") == "scored"
            for criterion in evaluation.get("criteria", [])
        )
        accurate = (
            expected is not None
            and actual is not None
            and abs(float(actual) - float(expected)) <= 0.5
        )
        rows.append(
            {
                "item_id": item_id,
                "expected": expected,
                "actual": actual,
                "criteria": scored_criteria,
                "accurate": accurate if actual is not None else None,
                "permission": labels.get(item_id, {}).get("permission", {}).get("status"),
                "latency_ms": payload.get("latency_ms"),
                "model": evaluation.get("provenance", {}).get("llm_model"),
            }
        )
    scorable = [row for row in rows if row["accurate"] is not None]
    accuracy = (
        sum(row["accurate"] for row in scorable) / len(scorable)
        if scorable
        else None
    )
    return rows, accuracy


def load_metrics(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report["metrics"]
    p95_names = (
        "goa_chat_duration_ms",
        "goa_match_duration_ms",
        "goa_essay_evaluation_duration_ms",
        "goa_speaking_time_to_first_transcript_ms",
        "ws_session_duration",
        "http_req_duration",
    )
    return {
        "p95_ms": {name: metrics.get(name, {}).get("p(95)") for name in p95_names},
        "checks": metrics.get("checks", {}),
        "vus_max": metrics.get("vus_max", {}).get("max"),
        "server_errors": metrics.get("goa_server_errors", {}).get("count"),
        "rate_limited": metrics.get("goa_rate_limited", {}).get("count"),
    }


def render_speaking_html(rows: list[dict[str, Any]], accuracy: float | None) -> str:
    body = []
    for row in rows:
        verdict = "NOT SCORABLE" if row["accurate"] is None else ("ACCURATE" if row["accurate"] else "OUTSIDE ±0.5")
        body.append(
            "<tr>"
            f"<td>{html.escape(row['item_id'])}</td>"
            f"<td>{row['expected']}</td><td>{row['actual'] if row['actual'] is not None else '—'}</td>"
            f"<td>{row['criteria']}/4</td><td>{verdict}</td>"
            f"<td>{html.escape(str(row['permission']))}</td>"
            f"<td>{row['latency_ms']}</td></tr>"
        )
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>GOA Speaking evaluation</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;color:#172033}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border:1px solid #ccd3df;text-align:left}}th{{background:#eef2f7}}.fail{{color:#a11;font-weight:700}}code{{background:#eef2f7;padding:2px 4px}}</style>
<h1>Speaking scorer evaluation</h1>
<p class="fail">Strict accuracy: {percent(accuracy)} — {'PASS' if strict_gate(accuracy) else 'FAIL'} (required &gt;80%).</p>
<p>Accuracy means the published overall score is within ±0.5 band of the validated reference. Pronunciation correctly abstains for transcript-only evidence. All official IELTS rows remain <code>quarantine</code> because permission is pending, so this report is exploratory and non-gating.</p>
<table><thead><tr><th>Item</th><th>Reference</th><th>GOA</th><th>Criteria</th><th>Verdict</th><th>Permission</th><th>Latency ms</th></tr></thead><tbody>{''.join(body)}</tbody></table>
</html>"""


def compile_results() -> dict[str, Any]:
    rag = read_json(RAG_REPORT)
    writing = read_json(WRITING_REPORT)
    manifest = read_json(SPEAKING_MANIFEST)
    speaking, speaking_accuracy = speaking_rows(manifest, SPEAKING_SCORES)
    authoritative_load = load_metrics(read_json(LOAD_AUTHORITATIVE))
    latest_load = load_metrics(read_json(LOAD_LATEST))
    trace = read_json(LANGFUSE)
    rag_accuracy = rag["quality"]["all"]["recall_at_10"]
    writing_accuracy = writing["metrics"]["writing_accuracy"]
    return {
        "overall": "PASS" if all(
            strict_gate(value)
            for value in (rag_accuracy, writing_accuracy, speaking_accuracy)
        ) else "NOT PASSED",
        "rag": {
            "accuracy": rag_accuracy,
            "captured_at": rag["captured_at"],
            "n": rag["quality"]["all"]["n"],
            "entity": rag["quality"]["entity"]["recall_at_10"],
            "numeric": rag["quality"]["numeric"]["recall_at_10"],
            "p95_ms": rag["latency_ms"]["p95"],
            "pass": strict_gate(rag_accuracy),
        },
        "writing": {
            "accuracy": writing_accuracy,
            "n": writing["metrics"]["writing_n_validated"],
            "model": writing["judge_arms"]["independent"]["model"],
            "pass": strict_gate(writing_accuracy),
        },
        "speaking": {
            "accuracy": speaking_accuracy,
            "scorable": sum(row["accurate"] is not None for row in speaking),
            "rows": speaking,
            "pass": strict_gate(speaking_accuracy),
            "gating": False,
        },
        "security": {"defended": 11, "complied": 0, "inconclusive": 1},
        "performance": {
            "authoritative_file": LOAD_AUTHORITATIVE.name,
            "authoritative": authoritative_load,
            "latest_file": LOAD_LATEST.name,
            "latest": latest_load,
        },
        "langfuse": trace,
    }


def render_markdown(results: dict[str, Any]) -> str:
    rag = results["rag"]
    writing = results["writing"]
    speaking = results["speaking"]
    load = results["performance"]["authoritative"]
    latest = results["performance"]["latest"]
    trace = results["langfuse"]
    agent_rows = "\n".join(
        f"| {number} | {name} | {service} | {role} |"
        for number, name, service, role in AGENTS
    )
    p95 = load["p95_ms"]
    latest_checks = latest["checks"]
    return f"""# GOA Gold-tier evaluation (GOA-040)

**Compiled from repository evidence:** 2026-08-12
**Overall rubric status: {results['overall']}**

This is a self-assessment, not a declaration manufactured from the ticket. The committed evidence currently misses two strict `>80%` gates: RAG Recall@10 is {percent(rag['accuracy'])} and Writing ACCURATE is {percent(writing['accuracy'])}. The exploratory Speaking set is {percent(speaking['accuracy'])}, but remains non-gating because its source permissions are pending. Exactly 80% would not satisfy “above 80%”.

## Rubric summary

| Area | Result | Gate | Status |
|---|---:|---:|---|
| RAG golden-set Recall@10 | {percent(rag['accuracy'])} (n={rag['n']}) | >80% | **{'PASS' if rag['pass'] else 'FAIL'}** |
| Writing independent-judge ACCURATE | {percent(writing['accuracy'])} (n={writing['n']}) | >80% | **{'PASS' if writing['pass'] else 'FAIL'}** |
| Speaking within ±0.5 band | {percent(speaking['accuracy'])} (n={speaking['scorable']}) | >80% | **{'PASS' if speaking['pass'] else 'FAIL'}**, non-gating |
| OWASP LLM adversarial run | 11 defended, 0 complied, 1 inconclusive | no compliance | **PASS with limitation** |
| Match P95 | {p95['goa_match_duration_ms']:.0f} ms | <5,000 ms | **PASS** |
| Chat P95 | {p95['goa_chat_duration_ms']:.0f} ms | <5,000 ms | **FAIL** |
| Speaking first transcript P95 | {p95['goa_speaking_time_to_first_transcript_ms']:.0f} ms | restated <45,000 ms | **PASS (restated)** |
| Langfuse archived trace | {trace['observation_count']} observations, ${trace['total_cost_usd']:.8f} | full 11-span trace | **PARTIAL** |
| CloudWatch / Logs Insights | no AWS account | substitute Grafana/local logs | **SUBSTITUTED** |

## The 11-agent topology

These are the independently prompted/acting roles in the current code, not service names copied from an old diagram.

| # | Agent | Owner | Role / handoff |
|---:|---|---|---|
{agent_rows}

The real handoff is: browser → Gateway → Orchestration supervisor → selected service. RAG continues retrieval → rerank → confidence decision → answer generation. Writing fans out to four criterion examiners and aggregates. Speaking uses the interviewer during practice and fans out to four criterion examiners for scoring, with explicit abstention when acoustic evidence is absent.

The archived post-fix Langfuse trace proves `chat_request → supervisor_routing → downstream_call → rag-query → retrieval → answer-generation`; its generation used {trace['verified_hierarchy'][-1]['model']}, {trace['verified_hierarchy'][-1]['input_tokens']} input tokens and {trace['verified_hierarchy'][-1]['output_tokens']} output tokens. It does **not** contain all 11 roles in one trace. The ticket’s stronger claim therefore remains unmet rather than being inferred from code.

## RAG retrieval quality

Source: [`GOA/evals/benchmarks/hybrid.json`](../GOA/evals/benchmarks/hybrid.json), captured {rag['captured_at']} against a frozen 2,905-document corpus.

| Slice | Recall@10 |
|---|---:|
| All answerable questions | {percent(rag['accuracy'])} |
| Entity | {percent(rag['entity'])} |
| Numeric | {percent(rag['numeric'])} |

Retrieval+rereanking P95 was {rag['p95_ms']:.0f} ms. Numeric retrieval passes comfortably; overall quality does not pass the Gold gate.

## Writing and Speaking evaluation

- [Writing HTML report](gold-tier-evidence/writing-evaluation.html): independent judge `{writing['model']}`, {percent(writing['accuracy'])} ACCURATE over {writing['n']} officially banded essays. Small n is a validation limitation.
- [Speaking HTML report](gold-tier-evidence/speaking-evaluation.html): {percent(speaking['accuracy'])} over {speaking['scorable']} scorable transcript-only official rows. The source manifest marks permission `pending` and split `quarantine`; pronunciation is unavailable without audio. It is useful exploratory evidence, not a release gate.

## Security

The authenticated live-Gateway penetration run in [`GOA/docs/security/goa-034-evidence.md`](../GOA/docs/security/goa-034-evidence.md) recorded **11 defended, 0 complied, 1 inconclusive** across prompt injection, prompt extraction, obfuscation, multilingual evasion, and input-length attacks. The remaining case was an intermittent truncated stream; a manual rerun did not comply. Structured logs have no CloudWatch backend in this environment, so the CloudWatch Logs Insights screenshot cannot truthfully be supplied.

## Performance

The authoritative complete run is [`{results['performance']['authoritative_file']}`](../GOA/perf/reports/{results['performance']['authoritative_file']}): 63 maximum VUs, 787/787 functional checks, zero server errors. P95 values:

| Measure | P95 ms | Interpretation |
|---|---:|---|
| Match | {p95['goa_match_duration_ms']:.0f} | passes 5 s |
| Chat | {p95['goa_chat_duration_ms']:.0f} | fails 5 s |
| Essay evaluate | {p95['goa_essay_evaluation_duration_ms']:.1f} | percentile dominated by 429 responses; allowed max was 23.4 s |
| Speaking first transcript | {p95['goa_speaking_time_to_first_transcript_ms']:.0f} | CPU-STT bound; passes restated 45 s SLO, not original 3 s |
| Speaking session | {p95['ws_session_duration']:.0f} | end-to-end WebSocket session |
| All HTTP | {p95['http_req_duration']:.0f} | mixed endpoints |

The chronologically latest load attempt, [`{results['performance']['latest_file']}`](../GOA/perf/reports/{results['performance']['latest_file']}), had {latest_checks.get('passes', 0)} checks pass and {latest_checks.get('fails', 0)} fail, including zero successful speaking WebSocket upgrades. It is recorded as a failed later attempt and is not silently replaced by the better earlier run.

## Observability and evidence

- [Archived post-fix Langfuse trace JSON](../GOA/docs/evidence/GOA-027-langfuse-post-fix.json): real hierarchy, token counts, and ${trace['total_cost_usd']:.8f} total request cost.
- [Machine-readable Gold-tier result](gold-tier-evidence/gold-tier-results.json).
- [Writing report](gold-tier-evidence/writing-evaluation.html) and [Speaking report](gold-tier-evidence/speaking-evaluation.html).
- [GOA-047 live restore evidence](gold-tier-evidence/goa-047-live-reset.json) and [live chat contingency](gold-tier-evidence/goa-047-live-chat-contingency.md).
- [GOA-047 real ingestion corpus](gold-tier-evidence/goa-047-ingestion-corpus.json): 8,001 persisted documents after configured Europe filtering and deduplication.

The requested five screenshots are **not attached**. The session's in-app browser inventory was empty, so there was no real browser surface with which to capture the client, Grafana, or Langfuse. Placeholder images would be misleading. Consequently, the screenshot DoD and the requirement to watch the browser flow remain unmet even though the live Gateway/API path was exercised.

## Known limitations and substitutions

Inference currently defaults to `claude-opus-5` through the Anthropic-compatible AgentRouter endpoint; the attached historical evaluation and trace artifacts identify their measured model (`claude-opus-4-8`) explicitly. Embeddings use local `nomic-embed-text`; STT/TTS use the local speech sidecar.

AWS credentials and a provisioned AWS environment are absent, so Prometheus/Grafana replaces CloudWatch and local structured logs replace Logs Insights. This is an equivalent local observation path, not CloudWatch evidence. The speaking `<3 s` request is restated to the implemented `<45 s` time-to-first-transcript SLO because local CPU STT dominates. The archived `/metrics` evidence does not prove `goa_speaking_slo_violations_total == 0` during a new five-minute production simulation; that exact acceptance item remains unmet.

## Reproduction

```bash
cd GOA
python scripts/compile_gold_tier.py
docker compose exec -T -e DEMO_USER_PASSWORD=<local-demo-password> user-service node /workspace/scripts/seed-demo.ts reset
```

The second command restores GOA-047 through owning APIs and performs the live Gateway preflight in under 30 seconds. Follow [`Docs/demo-script.md`](demo-script.md) for the timed browser walkthrough.
"""


def main() -> None:
    results = compile_results()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "gold-tier-results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copyfile(WRITING_HTML, EVIDENCE / "writing-evaluation.html")
    (EVIDENCE / "speaking-evaluation.html").write_text(
        render_speaking_html(results["speaking"]["rows"], results["speaking"]["accuracy"]),
        encoding="utf-8",
    )
    (DOCS / "gold-tier-evaluation.md").write_text(
        render_markdown(results), encoding="utf-8"
    )
    print(
        f"Compiled GOA-040: {results['overall']} "
        f"(RAG {percent(results['rag']['accuracy'])}, "
        f"Writing {percent(results['writing']['accuracy'])}, "
        f"Speaking {percent(results['speaking']['accuracy'])})"
    )


if __name__ == "__main__":
    main()
