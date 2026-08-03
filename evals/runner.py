import argparse
import json
import os
import sys
import datetime
import httpx
import boto3
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ValidationError
from anthropic import Anthropic

from evals.judge import judge_evaluation, judge_all, JudgeVerdict, CRITERIA

class RagItem(BaseModel):
    question: str
    expected_answer_concepts: List[str]

class ScoringItem(BaseModel):
    profile: str
    expected_gate: str
    expected_soft_score: float

class SpeakingItem(BaseModel):
    transcript: str
    expected_band: float
    expected_criteria: Optional[Dict[str, float]] = None
    id: Optional[str] = None

class WritingItem(BaseModel):
    essay: str
    expected_band: float
    expected_criteria: Optional[Dict[str, float]] = None
    # Declared so validation does not strip it: model_dump() drops undeclared keys,
    # so every judged item and every report row was labelled "<unknown>" — a report
    # whose rows cannot be traced back to an essay.
    id: Optional[str] = None

class GoldenDataset(BaseModel):
    rag: List[RagItem]
    scoring: List[ScoringItem]
    speaking: List[SpeakingItem]
    writing: List[WritingItem]

class ReportMetrics(BaseModel):
    rag_accuracy: Optional[float] = None
    gate_accuracy: Optional[float] = None
    scoring_mae: Optional[float] = None
    speaking_accuracy: Optional[float] = None
    writing_accuracy: Optional[float] = None
    writing_input_tokens: Optional[int] = 0
    writing_output_tokens: Optional[int] = 0
    writing_cached_count: Optional[int] = 0

class RegressionDeltas(BaseModel):
    delta_rag: Optional[float] = None
    delta_gate: Optional[float] = None
    delta_scoring_mae: Optional[float] = None
    delta_speaking: Optional[float] = None
    delta_writing: Optional[float] = None

class ReportSchema(BaseModel):
    run_id: str
    metrics: ReportMetrics
    # Per-domain accuracy stats and per-criterion MAE. These existed only in memory
    # and in the HTML, so the JSON artifact CI uploads carried an accuracy number
    # with no breakdown behind it — and --compare-with had nothing to compare, which
    # silently disabled the regression half of the gate.
    domain_stats: Dict[str, Any] = {}
    mae: Dict[str, Any] = {}
    items: List[Dict[str, Any]] = []
    regression_vs_previous: RegressionDeltas
    timestamp: str
    git_sha: str


ACCURACY_FLOOR = 0.80
MAX_ACCURACY_DROP = 0.05
MIN_JUDGED_RATIO = 0.80

# Four criterion agents run per essay, each a full model call. The old 30s budget
# timed out under normal latency and the timeout was then scored as a band of 0.0.
WRITING_REQUEST_TIMEOUT = 180.0


def compute_accuracy(verdicts: List[JudgeVerdict]) -> Dict[str, Any]:
    """Accuracy over *judged* items only."""
    judged = [v for v in verdicts if not v.is_error]
    errored = [v for v in verdicts if v.is_error]
    accurate = [v for v in judged if v.verdict == "ACCURATE"]
    disagreements = [
        v for v in judged
        if v.judged_band is not None and abs(v.judged_band - v.expert_band) > 1.0
    ]

    total_in_tokens = sum(v.input_tokens for v in verdicts)
    total_out_tokens = sum(v.output_tokens for v in verdicts)
    cached_count = sum(1 for v in verdicts if v.cached)

    return {
        "accuracy": (len(accurate) / len(judged)) if judged else None,
        "judged": len(judged),
        "errored": len(errored),
        "accurate": len(accurate),
        "overscored": sum(1 for v in judged if v.verdict == "OVERSCORED"),
        "underscored": sum(1 for v in judged if v.verdict == "UNDERSCORED"),
        "disagreements": len(disagreements),
        "input_tokens": total_in_tokens,
        "output_tokens": total_out_tokens,
        "cached_count": cached_count,
    }


def compute_mae(verdicts: List[JudgeVerdict], domain: str = "writing") -> Dict[str, Any]:
    """Mean absolute error between agent criteria and expert criteria."""
    judged = [v for v in verdicts if not v.is_error]

    if not judged:
        return {"overall": None, "per_criterion": {}, "mean_signed_error": None}

    domain_key = "writing" if domain.startswith("writing") else domain
    domain_criteria = CRITERIA.get(domain_key, ("task_response", "coherence", "lexical", "grammar"))

    per_criterion = {}
    for criterion in domain_criteria:
        deltas = [
            abs(v.agent_criteria[criterion] - v.expert_criteria[criterion])
            for v in judged
            if criterion in (v.agent_criteria or {})
            and criterion in (v.expert_criteria or {})
        ]
        if deltas:
            per_criterion[criterion] = round(sum(deltas) / len(deltas), 3)

    overall_deltas = [abs(v.delta) for v in judged]
    signed_deltas = [v.delta for v in judged]

    # An empty per_criterion renders identically whether the criteria were compared
    # and agreed, or were never comparable at all. Say which. The officially banded
    # IELTS scripts publish only an overall band, so there is no per-criterion ground
    # truth to compute against — that is a property of the source, not a bug, but a
    # report that hides it invites "MAE per criterion" to be claimed as delivered.
    rows_with_expert_criteria = sum(1 for v in judged if v.expert_criteria)
    unavailable_reason = None
    if not per_criterion:
        unavailable_reason = (
            "no per-criterion ground truth in the dataset: the official IELTS sample "
            "scripts publish only an overall band"
            if rows_with_expert_criteria == 0
            else "agent returned no criterion bands to compare"
        )

    return {
        "overall": round(sum(overall_deltas) / len(judged), 3) if judged else None,
        "mean_signed_error": round(sum(signed_deltas) / len(judged), 3) if judged else None,
        "per_criterion": per_criterion,
        "per_criterion_unavailable_reason": unavailable_reason,
        "rows_with_expert_criteria": rows_with_expert_criteria,
    }


def check_regression_gate(current: dict, previous: dict | None) -> tuple[bool, list]:
    """Return (passed, messages).

    `current` maps DOMAIN NAME -> accuracy stats, and nothing else. It used to be
    handed the whole metrics dict, so `writing_mae` — a metrics key, not a domain —
    was walked as if it were a domain and failed the run with
    "COVERAGE: writing_mae produced no judged items at all". Keep the input to real
    domains so a new metric cannot invent a phantom failing domain again.
    """
    failures = []

    for domain, stats in current.items():
        if not isinstance(stats, dict):
            continue

        judged = stats.get("judged", 0)
        errored = stats.get("errored", 0)
        total = judged + errored

        if total > 0 and (judged / total) < MIN_JUDGED_RATIO:
            failures.append(
                f"COVERAGE: {domain} judged only {judged}/{total} items "
                f"({errored} errored) — accuracy over that subset is not meaningful"
            )
            continue

        accuracy = stats.get("accuracy")
        if accuracy is None:
            failures.append(f"COVERAGE: {domain} produced no judged items at all")
            continue

        if accuracy < ACCURACY_FLOOR:
            failures.append(
                f"FLOOR: {domain} accuracy {accuracy:.1%} is below the "
                f"{ACCURACY_FLOOR:.0%} target ({stats.get('accurate', 0)}/{judged})"
            )

        prior = (previous or {}).get(domain, {}).get("accuracy")
        if prior is not None:
            drop = prior - accuracy
            if drop > MAX_ACCURACY_DROP:
                failures.append(
                    f"REGRESSION: {domain} fell {drop:.1%} "
                    f"({prior:.1%} -> {accuracy:.1%}), limit is {MAX_ACCURACY_DROP:.0%}"
                )

    return (len(failures) == 0), failures


def load_golden_dataset(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            dataset = GoldenDataset(**data)
            return dataset.model_dump()
    except FileNotFoundError:
        print(f"Error: The file {path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: The file {path} contains invalid JSON.")
        return None
    except ValidationError as e:
        print(f"Error: Dataset schema validation failed for {path}: {e}")
        return None


def load_previous_report(path: str) -> dict:
    if not path:
        return {}
    if path.startswith("s3://"):
        try:
            parsed = urlparse(path)
            bucket = parsed.netloc
            key = parsed.path.lstrip('/')
            s3_client = boto3.client('s3', endpoint_url=os.environ.get('AWS_ENDPOINT_URL'))
            response = s3_client.get_object(Bucket=bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            print(f"Warning: Could not load previous report from S3: {e}")
            return {}
    else:
        try:
            with open(path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}


def run_rag_eval(data: dict) -> dict:
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    if not client.api_key:
        print("Warning: ANTHROPIC_API_KEY missing. Skipping RAG evaluation.")
        return {"rag_accuracy": None}

    passes = 0
    total = 0
    rag_url = os.environ.get("RAG_SERVICE_URL", "http://localhost:8084")
    
    for item in data.get('rag', []):
        total += 1
        payload = {"question": item["question"], "userId": "eval_test_user"}
        try:
            response = httpx.post(f"{rag_url}/query", json=payload, timeout=30.0)
            service_data = response.json()
        except Exception:
            service_data = {}
        
        prompt = f"""
        Evaluate if the provided text contains the expected concepts.
        Text: {service_data}
        Expected concepts: {item.get("expected_answer_concepts", [])}
        
        Respond with ONLY the exact word "PASS" or "FAIL".
        """
        try:
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=10,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}]
            )
            if "PASS" in message.content[0].text.strip():
                passes += 1
        except Exception:
            pass

    accuracy = (passes / total) if total > 0 else 0.0
    return {"rag_accuracy": accuracy}


def run_scoring_eval(data: dict) -> dict:
    gate_passes = 0
    total = 0
    soft_score_errors = []
    scoring_url = os.environ.get("SCORING_SERVICE_URL", "http://localhost:8084")
    
    for item in data.get('scoring', []):
        total += 1
        payload = {"userId": item["profile"], "programId": "99999999-9999-9999-9999-999999999999"}
        try:
            response = httpx.post(f"{scoring_url}/scoring/score", json=payload, timeout=30.0)
            service_data = response.json()
            gate = "blocked" if service_data.get("blocked_by") else "pass"
            if gate == item.get("expected_gate"):
                gate_passes += 1
                
            soft_score = service_data.get("score", 0.0)
            mae = abs(soft_score - item.get("expected_soft_score", 0.0))
            soft_score_errors.append(mae)
        except Exception:
            soft_score_errors.append(100.0)

    gate_accuracy = (gate_passes / total) if total > 0 else 0.0
    scoring_mae = sum(soft_score_errors) / len(soft_score_errors) if soft_score_errors else 0.0

    return {"gate_accuracy": gate_accuracy, "scoring_mae": scoring_mae}


def run_speaking_eval(data: dict) -> dict:
    print("Warning: Speaking Eval is WS-only. Skipping bare-LLM execution.")
    return {"speaking_accuracy": None}


# The writing service and the eval vocabulary disagree on two of the four criterion
# names. Left untranslated, per-criterion MAE silently computes over an empty
# intersection and reports {} — a metric that looks present and measures nothing.
SERVICE_TO_EVAL_CRITERION = {
    "task_response": "task_response",
    "cohesion": "coherence",
    "vocabulary": "lexical",
    "grammar": "grammar",
}


def _normalise_agent_result(payload: dict) -> dict:
    """Flatten the service's `evaluations` list into the `criteria` dict the judge reads."""
    criteria = {}
    for entry in payload.get("evaluations") or []:
        name = SERVICE_TO_EVAL_CRITERION.get(entry.get("criterion"))
        if name is not None and entry.get("band_score") is not None:
            criteria[name] = float(entry["band_score"])
    return {
        "overall_band": payload.get("overall_band"),
        "criteria": criteria,
        "justification": payload.get("justification"),
    }


def run_writing_eval(data: dict, judge_client=None) -> dict:
    writing_url = os.environ.get("WRITING_SERVICE_URL", "http://localhost:8000")
    items = data.get('writing', [])
    agent_results = []

    for item in items:
        payload = {
            "userId": "eval_test_user",
            "essayText": item["essay"],
            "submissionType": "typed_text",
            "examType": "IELTS Writing"
        }
        try:
            response = httpx.post(f"{writing_url}/essays/evaluate", json=payload,
                                  timeout=WRITING_REQUEST_TIMEOUT)
            response.raise_for_status()
            body = response.json()
            if body.get("overall_band") is None:
                # A response without a band is a broken call, not a candidate who
                # scored zero. Recording 0.0 here is what made a dead port look like
                # 0% agent accuracy: every item came back UNDERSCORED against a band
                # the agent never actually produced.
                raise ValueError(f"response carried no overall_band: {str(body)[:200]}")
            agent_results.append(_normalise_agent_result(body))
        except Exception as e:
            agent_results.append({"agent_error": f"{type(e).__name__}: {e}"})

    verdicts = judge_all("writing", items, agent_results, client=judge_client, max_workers=4)
    accuracy_stats = compute_accuracy(verdicts)
    mae_stats = compute_mae(verdicts, domain="writing")
    
    return {
        "writing_accuracy": accuracy_stats["accuracy"],
        "writing_stats": accuracy_stats,
        "writing_mae": mae_stats,
        "writing_verdicts": verdicts,
        "writing_input_tokens": accuracy_stats["input_tokens"],
        "writing_output_tokens": accuracy_stats["output_tokens"],
        "writing_cached_count": accuracy_stats["cached_count"],
    }


def upload_report(report_path: str, s3_upload_path: str) -> bool:
    """Publish the report, and refresh `latest_report.json`.

    `--s3-upload-path` was parsed and then never used. Because CI compares against
    s3://goa-eval-reports/latest_report.json and nothing ever wrote that key, the
    comparison silently found nothing on every run — the regression half of the gate
    has never once fired in CI. Updating `latest_report.json` is the part that makes
    --compare-with mean anything on the next PR.
    """
    try:
        parsed = urlparse(s3_upload_path)
        bucket = parsed.netloc
        prefix = parsed.path.strip("/")
        key = f"{prefix}/{os.path.basename(report_path)}" if prefix else os.path.basename(report_path)

        s3_client = boto3.client("s3", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        with open(report_path, "rb") as handle:
            body = handle.read()
        s3_client.put_object(Bucket=bucket, Key=key, Body=body,
                             ContentType="application/json")
        latest_key = f"{prefix}/latest_report.json" if prefix else "latest_report.json"
        s3_client.put_object(Bucket=bucket, Key=latest_key, Body=body,
                             ContentType="application/json")
        print(f"Report uploaded to s3://{bucket}/{key} (and {latest_key})")
        return True
    except Exception as e:
        # Never fail the run on a publishing problem: the gate's verdict is the
        # product, the upload is bookkeeping.
        print(f"Warning: Could not upload report to {s3_upload_path}: {e}")
        return False


def format_pr_comment(domain_stats: dict, mae_by_domain: dict,
                      gate_failures: list, gate_passed: bool) -> str:
    """The PR comment body the ticket's DoD asks for."""
    lines = [
        "## Eval report",
        "",
        f"**Gate: {'PASS' if gate_passed else 'FAIL'}**",
        "",
        "| Domain | Accuracy | Judged | Errored | MAE (overall) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for domain, stats in sorted(domain_stats.items()):
        accuracy = stats.get("accuracy")
        accuracy_text = f"{accuracy:.1%}" if accuracy is not None else "n/a"
        mae = (mae_by_domain.get(domain) or {}).get("overall")
        lines.append(
            f"| {domain} | {accuracy_text} | {stats.get('judged', 0)} "
            f"| {stats.get('errored', 0)} | {mae if mae is not None else 'n/a'} |"
        )

    if not domain_stats:
        lines.append("| _none measured_ | | | | |")

    # State n next to the number. Three items cannot carry a percentage without it.
    judged_total = sum(s.get("judged", 0) for s in domain_stats.values())
    lines += ["", f"_n = {judged_total} judged item(s)._"]

    if gate_failures:
        lines += ["", "### Failures"] + [f"- {f}" for f in gate_failures]
    return "\n".join(lines)


def write_pr_summary(domain_stats: dict, mae_by_domain: dict,
                     gate_failures: list, gate_passed: bool) -> None:
    """Write to GITHUB_STEP_SUMMARY and a file the workflow posts as a PR comment."""
    body = format_pr_comment(domain_stats, mae_by_domain, gate_failures, gate_passed)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(body + "\n")
        except Exception as e:
            print(f"Warning: Could not write step summary: {e}")

    comment_path = os.path.join(os.path.dirname(__file__), "reports", "pr_comment.md")
    try:
        with open(comment_path, "w", encoding="utf-8") as handle:
            handle.write(body + "\n")
        print(f"PR comment body written to {comment_path}")
    except Exception as e:
        print(f"Warning: Could not write PR comment body: {e}")


def _calc_delta(current, prev):
    if current is None or prev is None:
        return None
    return current - prev


def main():
    parser = argparse.ArgumentParser(description="End-to-end evaluation suite")
    parser.add_argument("--domains", type=str, default="writing,speaking", help="Comma-separated domains to evaluate")
    parser.add_argument("--compare-with", type=str, default=None)
    parser.add_argument("--s3-upload-path", type=str, default=None)
    args = parser.parse_args()

    active_domains = set(args.domains.split(","))

    dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    dataset = load_golden_dataset(dataset_path)
    if not dataset:
        sys.exit(1)

    prev_reports = {}
    if args.compare_with:
        prev_reports = load_previous_report(args.compare_with)

    metrics = {}
    if "rag" in active_domains:
        metrics.update(run_rag_eval(dataset))
    if "scoring" in active_domains:
        metrics.update(run_scoring_eval(dataset))
    if "speaking" in active_domains:
        metrics.update(run_speaking_eval(dataset))
    if "writing" in active_domains:
        metrics.update(run_writing_eval(dataset))

    # Only real domains reach the gate.
    domain_stats = {}
    if metrics.get("writing_stats"):
        domain_stats["writing"] = metrics["writing_stats"]
    if metrics.get("speaking_stats"):
        domain_stats["speaking"] = metrics["speaking_stats"]

    mae_by_domain = {}
    if metrics.get("writing_mae"):
        mae_by_domain["writing"] = metrics["writing_mae"]

    item_rows = [
        {
            "id": v.item_id,
            "verdict": v.verdict,
            "agent_band": None if v.is_error else v.agent_band,
            "expert_band": v.expert_band,
            "judged_band": v.judged_band,
            "delta": None if v.is_error else v.delta,
            "reason": v.reason,
            "error": v.error,
        }
        for v in (metrics.get("writing_verdicts") or [])
    ]

    prev_metrics = prev_reports.get("metrics", {})
    deltas = {
        "delta_rag": _calc_delta(metrics.get("rag_accuracy"), prev_metrics.get("rag_accuracy")),
        "delta_gate": _calc_delta(metrics.get("gate_accuracy"), prev_metrics.get("gate_accuracy")),
        "delta_scoring_mae": _calc_delta(metrics.get("scoring_mae"), prev_metrics.get("scoring_mae")),
        "delta_speaking": _calc_delta(metrics.get("speaking_accuracy"), prev_metrics.get("speaking_accuracy")),
        "delta_writing": _calc_delta(metrics.get("writing_accuracy"), prev_metrics.get("writing_accuracy"))
    }

    report = ReportSchema(
        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        metrics=ReportMetrics(
            rag_accuracy=metrics.get("rag_accuracy"),
            gate_accuracy=metrics.get("gate_accuracy"),
            scoring_mae=metrics.get("scoring_mae"),
            speaking_accuracy=metrics.get("speaking_accuracy"),
            writing_accuracy=metrics.get("writing_accuracy"),
            writing_input_tokens=metrics.get("writing_input_tokens", 0),
            writing_output_tokens=metrics.get("writing_output_tokens", 0),
            writing_cached_count=metrics.get("writing_cached_count", 0),
        ),
        domain_stats=domain_stats,
        mae=mae_by_domain,
        items=item_rows,
        regression_vs_previous=RegressionDeltas(**deltas),
        timestamp=datetime.datetime.utcnow().isoformat() + "Z",
        git_sha=os.environ.get("GITHUB_SHA", "unknown")
    )

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    filename = f"{report.timestamp.replace(':', '')}.json"
    report_path = os.path.join(reports_dir, filename)
    
    # encoding is explicit: the default is cp1252 on Windows, and the first judge
    # reason containing an em-dash wrote a file that json.load could not read back.
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))
        
    print(f"Report written to {report_path}")

    # Generate HTML report
    try:
        from evals.report_generator import render_html_report
        html_content = render_html_report(
            report_dict=report.model_dump(),
            domain_stats=metrics,
            writing_mae=metrics.get("writing_mae"),
            writing_verdicts=metrics.get("writing_verdicts")
        )
        html_path = report_path.replace(".json", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"HTML Report written to {html_path}")
    except Exception as e:
        print(f"Warning: Could not render HTML report: {e}")

    if args.s3_upload_path:
        upload_report(report_path, args.s3_upload_path)

    # Check regression gate across evaluated domains
    gate_passed, gate_failures = check_regression_gate(
        domain_stats, prev_reports.get("domain_stats")
    )

    write_pr_summary(domain_stats, mae_by_domain, gate_failures, gate_passed)

    if not gate_passed:
        for fail_msg in gate_failures:
            print(f"FAIL: {fail_msg}")
        sys.exit(1)

    print("PASS: All evaluations met targets.")
    sys.exit(0)


if __name__ == "__main__":
    main()