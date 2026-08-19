import argparse
import json
import os
import sys
import datetime
import uuid
import httpx
import boto3
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from anthropic import Anthropic

from evals.consistency import run_consistency
from evals.judge import (
    CRITERIA,
    JudgeVerdict,
    get_model,
    judge_evaluation,
    judge_all,
)
from evals.speaking.manifest.validate import (
    gating_items as speaking_gating_items,
    load_manifest as load_speaking_manifest,
    validate as validate_speaking_manifest,
)

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
    band_source: str
    label_validated: bool

class WritingItem(BaseModel):
    essay: str
    expected_band: float
    expected_criteria: Optional[Dict[str, float]] = None
    # Declared so validation does not strip it: model_dump() drops undeclared keys,
    # so every judged item and every report row was labelled "<unknown>" — a report
    # whose rows cannot be traced back to an essay.
    id: Optional[str] = None
    band_source: str
    label_validated: bool

class GoldenDataset(BaseModel):
    rag: List[RagItem]
    scoring: List[ScoringItem]
    speaking: List[SpeakingItem]
    writing: List[WritingItem]
    writing_synthetic_unvalidated: List[WritingItem] = Field(default_factory=list)

class ReportMetrics(BaseModel):
    rag_accuracy: Optional[float] = None
    gate_accuracy: Optional[float] = None
    scoring_mae: Optional[float] = None
    speaking_accuracy: Optional[float] = None
    speaking_reason: Optional[str] = None
    speaking_pipeline_exercised: bool = False
    writing_accuracy: Optional[float] = None
    writing_n_validated: int = 0
    accuracy_caveat: Optional[str] = None
    writing_input_tokens: Optional[int] = None
    writing_output_tokens: Optional[int] = None
    writing_cached_count: Optional[int] = None

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
    domain_stats: Dict[str, Any] = Field(default_factory=dict)
    mae: Dict[str, Any] = Field(default_factory=dict)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    judge_model: str
    grader_models: List[str]
    judge_arms: Dict[str, Any] = Field(default_factory=dict)
    judge_family_delta: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    consistency: Dict[str, Any] = Field(default_factory=dict)
    regression_vs_previous: RegressionDeltas
    timestamp: str
    git_sha: str


ACCURACY_FLOOR = 0.80
MAX_ACCURACY_DROP = 0.05
MIN_JUDGED_RATIO = 0.80

# Four criterion agents run per essay, each a full model call. The old 30s budget
# timed out under normal latency and the timeout was then scored as a band of 0.0.
WRITING_REQUEST_TIMEOUT = float(
    os.environ.get("EVAL_WRITING_REQUEST_TIMEOUT_SECONDS", "600")
)


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


def check_regression_gate(
    current: dict,
    previous: dict | None,
    current_consistency: dict | None = None,
    previous_consistency: dict | None = None,
) -> tuple[bool, list]:
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

    for domain, stats in (current_consistency or {}).items():
        n_calls = stats.get("n_calls")
        expected_calls = stats.get("expected_calls")
        if (
            n_calls is not None
            and expected_calls is not None
            and n_calls != expected_calls
        ):
            failures.append(
                f"CONSISTENCY COVERAGE: {domain} completed {n_calls}/"
                f"{expected_calls} repeat calls"
            )
        current_std_dev = (stats.get("domain") or {}).get("std_dev")
        prior_std_dev = (
            ((previous_consistency or {}).get(domain) or {}).get("domain") or {}
        ).get("std_dev")
        if (
            current_std_dev is not None
            and prior_std_dev is not None
            and current_std_dev > prior_std_dev
        ):
            failures.append(
                f"CONSISTENCY REGRESSION: {domain} std_dev rose from "
                f"{prior_std_dev:.4f} to {current_std_dev:.4f}"
            )

    return (len(failures) == 0), failures


def compute_provenance(data: dict) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    for domain, rows in data.items():
        if not isinstance(rows, list) or not rows:
            continue
        if not all(isinstance(row, dict) and "band_source" in row for row in rows):
            continue
        provenance[domain] = {
            "n_total": len(rows),
            "n_validated": sum(row.get("label_validated") is True for row in rows),
            "n_synthetic": sum(row.get("label_validated") is False for row in rows),
            "band_source": sorted({row["band_source"] for row in rows}),
        }
    return provenance


def load_golden_dataset(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            dataset = GoldenDataset(**data)
            loaded = dataset.model_dump()
            loaded["provenance"] = compute_provenance(loaded)
            return loaded
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
    """Report what each lane can currently measure (SPEAK-EVAL-007).

    This used to return `None` with a hardcoded sentence. The sentence was
    honest but frozen: it would have kept printing unchanged after the dataset
    was fixed. Now each lane is asked what it can run, and says so.

    A lane with no eligible items reports `not_run` with the reason, never a
    number. The acceptance criterion is that requesting speaking cannot return
    null while the job passes -- so the structure is always present and always
    names its state, which is a different thing from always having a score.
    """
    from evals.speaking.agreement import compute_agreement
    from evals.speaking.lanes import LANE_SPECS, Lane, eligible_items

    try:
        manifest = load_speaking_manifest()
        governance = [str(p) for p in validate_speaking_manifest(manifest)]
    except Exception as exc:
        return {
            "speaking_accuracy": None,
            "speaking_reason": (
                f"not measured: the speaking dataset manifest could not be read "
                f"({type(exc).__name__}: {exc})"
            ),
            "speaking_pipeline_exercised": False,
            "speaking_lanes": {},
        }

    lanes: dict[str, dict] = {}
    for lane, spec in LANE_SPECS.items():
        items = [] if governance else eligible_items(manifest, lane)
        entry = {
            "eligible_items": len(items),
            "exercises": list(spec.exercises),
            "requires": sorted(spec.requires),
            "description": spec.description,
            "state": "not_run",
            "accuracy": None,
            "metrics": None,
        }
        if governance:
            entry["reason"] = (
                f"the dataset manifest has {len(governance)} governance problem(s); "
                f"no lane may publish a number over an unsafe dataset"
            )
        elif not items:
            entry["reason"] = (
                f"no item provides {' and '.join(sorted(spec.requires))}. "
                f"{_speaking_source_hint(lane)}"
            )
        else:
            # Scoring adapters land with the lane runners. Until then the lane
            # reports that it HAS work rather than silently reporting nothing --
            # the two states must not look alike.
            entry["state"] = "pending_runner"
            entry["reason"] = (
                f"{len(items)} eligible item(s); the {lane.value} runner is not "
                f"wired to the service yet"
            )
        lanes[lane.value] = entry

    total_eligible = sum(entry["eligible_items"] for entry in lanes.values())
    if governance:
        reason = (
            f"not measured: {len(governance)} dataset governance problem(s) must be "
            f"resolved before any speaking number can be published"
        )
    elif total_eligible == 0:
        quarantined = len(manifest.get("items", []))
        reason = (
            f"not measured: {quarantined} speaking item(s) are registered and none is "
            f"cleared to gate any lane. The official IELTS samples carry examiner "
            f"bands but their permission status is unreviewed; the remaining rows are "
            f"model-written with model-assigned bands"
        )
    else:
        reason = (
            f"not measured: {total_eligible} eligible item(s) across "
            f"{sum(1 for e in lanes.values() if e['eligible_items'])} lane(s), "
            f"runners not yet wired"
        )

    print(f"Warning: Speaking accuracy {reason}.")
    for name, entry in lanes.items():
        print(f"  {name:<14} {entry['eligible_items']:>3} items  {entry['state']}")

    return {
        "speaking_accuracy": None,
        "speaking_reason": reason,
        # False until a lane that traverses audio actually runs. The scorer lane
        # alone must never set this true: claiming the pipeline was exercised on
        # transcript-only evidence is the reporting-layer version of the defect
        # SPEAK-EVAL-002 fixed in the code.
        "speaking_pipeline_exercised": False,
        "speaking_lanes": lanes,
        "speaking_manifest": {
            "total_items": len(manifest.get("items", [])),
            "gating_items": len(speaking_gating_items(manifest)),
            "governance_problems": governance,
        },
    }


def _speaking_source_hint(lane) -> str:
    """Say what would make this lane runnable, not just that it is not."""
    from evals.speaking.lanes import Lane

    if lane is Lane.SCORER_ONLY:
        return (
            "The official IELTS samples provide transcripts and examiner bands but "
            "their permission status is `pending`; review the terms to clear them."
        )
    return (
        "No licensed recording has been acquired. Audio lanes need a source with "
        "both a recording and a human band (SPEAK-EVAL-004 source hierarchy)."
    )


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
        "from_cache": payload.get("from_cache"),
    }


def _request_writing(
    item: dict,
    *,
    user_id: str,
    submission_type: str,
) -> dict:
    writing_url = os.environ.get("WRITING_SERVICE_URL", "http://localhost:8000")
    response = httpx.post(
        f"{writing_url}/essays/evaluate",
        json={
            "userId": user_id,
            "essayText": item["essay"],
            "submissionType": submission_type,
            "examType": "IELTS Writing",
        },
        timeout=WRITING_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("overall_band") is None:
        raise ValueError(f"response carried no overall_band: {str(body)[:200]}")
    return _normalise_agent_result(body)


def _serialise_verdict(verdict: JudgeVerdict) -> dict[str, Any]:
    return {
        "item_id": verdict.item_id,
        "verdict": verdict.verdict,
        "agent_band": None if verdict.is_error else verdict.agent_band,
        "expert_band": verdict.expert_band,
        "judged_band": verdict.judged_band,
        "delta": None if verdict.is_error else verdict.delta,
        "reason": verdict.reason,
        "error": verdict.error,
    }


def _judge_arm(model: str, verdicts: list[JudgeVerdict]) -> dict[str, Any]:
    accuracy = compute_accuracy(verdicts)
    mae = compute_mae(verdicts, domain="writing")
    try:
        from goa_pricing import cost_usd

        cost = cost_usd(model, accuracy["input_tokens"], accuracy["output_tokens"])
    except Exception:
        cost = None
    return {
        "model": model,
        "accuracy": accuracy,
        "mae": mae,
        "cost_usd": cost,
        "verdicts": [_serialise_verdict(verdict) for verdict in verdicts],
    }


def compute_judge_family_delta(
    same_family: dict[str, Any], independent: dict[str, Any]
) -> dict[str, Any]:
    same_by_id = {row["item_id"]: row for row in same_family["verdicts"]}
    independent_by_id = {
        row["item_id"]: row for row in independent["verdicts"]
    }
    changed = [
        item_id
        for item_id in sorted(same_by_id)
        if same_by_id[item_id]["verdict"]
        != independent_by_id[item_id]["verdict"]
    ]
    judged_band_deltas = {}
    for item_id in sorted(same_by_id):
        left = same_by_id[item_id]["judged_band"]
        right = independent_by_id[item_id]["judged_band"]
        judged_band_deltas[item_id] = (
            round(right - left, 3)
            if left is not None and right is not None
            else None
        )
    same_accuracy = same_family["accuracy"]["accuracy"]
    independent_accuracy = independent["accuracy"]["accuracy"]
    same_mae = same_family["mae"]["overall"]
    independent_mae = independent["mae"]["overall"]
    return {
        "accuracy_delta": (
            independent_accuracy - same_accuracy
            if independent_accuracy is not None and same_accuracy is not None
            else None
        ),
        "mae_delta": (
            independent_mae - same_mae
            if independent_mae is not None and same_mae is not None
            else None
        ),
        "verdicts_changed": len(changed),
        "changed_item_ids": changed,
        "judged_band_deltas": judged_band_deltas,
    }


def run_writing_eval(
    data: dict,
    judge_client=None,
    judge_clients: Optional[Dict[str, Any]] = None,
) -> dict:
    items = [
        item
        for item in data.get("writing", [])
        if item.get("label_validated") is True
    ]
    agent_results = []
    run_nonce = uuid.uuid4().hex

    for item in items:
        try:
            agent_results.append(
                _request_writing(
                    item,
                    user_id=f"eval-writing-{run_nonce}",
                    submission_type=f"typed_text_eval_{run_nonce}_{item.get('id')}",
                )
            )
        except Exception as e:
            agent_results.append({"agent_error": f"{type(e).__name__}: {e}"})

    independent_model = get_model()
    grader_models = sorted(
        {os.environ.get("WRITING_MODEL", "claude-opus-5")}
    )
    same_family_model = grader_models[0]
    clients = judge_clients or {}
    if judge_client is not None:
        clients = {**clients, independent_model: judge_client}
    same_verdicts = judge_all(
        "writing",
        items,
        agent_results,
        client=clients.get(same_family_model),
        max_workers=4,
        model=same_family_model,
    )
    independent_verdicts = judge_all(
        "writing",
        items,
        agent_results,
        client=clients.get(independent_model),
        max_workers=4,
        model=independent_model,
    )
    same_arm = _judge_arm(same_family_model, same_verdicts)
    independent_arm = _judge_arm(independent_model, independent_verdicts)
    accuracy_stats = independent_arm["accuracy"]
    mae_stats = independent_arm["mae"]
    n_validated = len(items)
    caveat = (
        f"n={n_validated} — not a validation; see band_source"
        if n_validated < 10
        else None
    )
    
    return {
        "writing_accuracy": accuracy_stats["accuracy"],
        "writing_n_validated": n_validated,
        "accuracy_caveat": caveat,
        "writing_stats": accuracy_stats,
        "writing_mae": mae_stats,
        "writing_verdicts": independent_verdicts,
        "writing_input_tokens": accuracy_stats["input_tokens"],
        "writing_output_tokens": accuracy_stats["output_tokens"],
        "writing_cached_count": accuracy_stats["cached_count"],
        "judge_model": independent_model,
        "grader_models": grader_models,
        "judge_arms": {
            "same_family": same_arm,
            "independent": independent_arm,
        },
        "judge_family_delta": compute_judge_family_delta(
            same_arm, independent_arm
        ),
    }


def run_writing_consistency(data: dict, repeats: int = 5) -> dict[str, Any]:
    items = [
        item
        for item in data.get("writing", [])
        if item.get("label_validated") is True
    ]
    user_id = f"eval-consistency-{uuid.uuid4().hex}"

    def evaluate(item: dict, repeat: int, telemetry_user_id: str) -> dict:
        return _request_writing(
            item,
            user_id=telemetry_user_id,
            submission_type=(
                f"c_{uuid.uuid4().hex[:12]}_"
                f"{item.get('id')}_{repeat}"
            ),
        )

    return run_consistency(
        items,
        evaluate,
        repeats=repeats,
        user_id=user_id,
        model=os.environ.get("WRITING_MODEL", "claude-opus-5"),
    )


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
    parser.add_argument(
        "--consistency",
        action="store_true",
        help="Run repeated real grader calls and publish self-consistency",
    )
    parser.add_argument("--repeats", type=int, default=5)
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

    consistency = {}
    if args.consistency and "writing" in active_domains:
        consistency["writing"] = run_writing_consistency(
            dataset, repeats=args.repeats
        )

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
            speaking_reason=metrics.get("speaking_reason"),
            speaking_pipeline_exercised=metrics.get(
                "speaking_pipeline_exercised", False
            ),
            writing_accuracy=metrics.get("writing_accuracy"),
            writing_n_validated=metrics.get("writing_n_validated", 0),
            accuracy_caveat=metrics.get("accuracy_caveat"),
            writing_input_tokens=metrics.get("writing_input_tokens"),
            writing_output_tokens=metrics.get("writing_output_tokens"),
            writing_cached_count=metrics.get("writing_cached_count"),
        ),
        domain_stats=domain_stats,
        mae=mae_by_domain,
        items=item_rows,
        judge_model=metrics.get("judge_model", get_model()),
        grader_models=metrics.get(
            "grader_models",
            [os.environ.get("WRITING_MODEL", "claude-opus-5")],
        ),
        judge_arms=metrics.get("judge_arms", {}),
        judge_family_delta=metrics.get("judge_family_delta", {}),
        provenance=dataset.get("provenance", {}),
        consistency=consistency,
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
            domain_stats=domain_stats,
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
        domain_stats,
        prev_reports.get("domain_stats"),
        consistency,
        prev_reports.get("consistency"),
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
