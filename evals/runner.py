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

class WritingItem(BaseModel):
    essay: str
    expected_band: float
    expected_criteria: Optional[Dict[str, float]] = None

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
    regression_vs_previous: RegressionDeltas
    timestamp: str
    git_sha: str


ACCURACY_FLOOR = 0.80
MAX_ACCURACY_DROP = 0.05
MIN_JUDGED_RATIO = 0.80


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

    return {
        "overall": round(sum(overall_deltas) / len(judged), 3) if judged else None,
        "mean_signed_error": round(sum(signed_deltas) / len(judged), 3) if judged else None,
        "per_criterion": per_criterion,
    }


def check_regression_gate(current: dict, previous: dict | None) -> tuple[bool, list]:
    """Return (passed, messages)."""
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
            response = httpx.post(f"{writing_url}/essays/evaluate", json=payload, timeout=30.0)
            agent_results.append(response.json())
        except Exception as e:
            agent_results.append({"overall_band": 0.0, "criteria": {}, "error": str(e)})

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
        regression_vs_previous=RegressionDeltas(**deltas),
        timestamp=datetime.datetime.utcnow().isoformat() + "Z",
        git_sha=os.environ.get("GITHUB_SHA", "unknown")
    )

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    filename = f"{report.timestamp.replace(':', '')}.json"
    report_path = os.path.join(reports_dir, filename)
    
    with open(report_path, "w") as f:
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

    # Check regression gate across evaluated metrics
    gate_passed, gate_failures = check_regression_gate(metrics, prev_reports)
    if not gate_passed:
        for fail_msg in gate_failures:
            print(f"FAIL: {fail_msg}")
        sys.exit(1)

    print("PASS: All evaluations met targets.")
    sys.exit(0)


if __name__ == "__main__":
    main()