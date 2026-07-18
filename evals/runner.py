import argparse
import json
import os
import sys
import datetime
import httpx
import boto3
from urllib.parse import urlparse
from typing import List, Optional
from pydantic import BaseModel, ValidationError
from anthropic import Anthropic

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

class WritingItem(BaseModel):
    essay: str
    expected_band: float

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
    
    # If API key is missing, exclude the metric entirely
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
            
            # True response parsing: "blocked_by" null means pass
            gate = "blocked" if service_data.get("blocked_by") else "pass"
            if gate == item.get("expected_gate"):
                gate_passes += 1
                
            soft_score = service_data.get("score", 0.0)
            mae = abs(soft_score - item.get("expected_soft_score", 0.0))
            soft_score_errors.append(mae)
        except Exception as e:
            # penalize heavily
            soft_score_errors.append(100.0)

    gate_accuracy = (gate_passes / total) if total > 0 else 0.0
    scoring_mae = sum(soft_score_errors) / len(soft_score_errors) if soft_score_errors else 0.0

    return {"gate_accuracy": gate_accuracy, "scoring_mae": scoring_mae}

def run_speaking_eval(data: dict) -> dict:
    # TODO: Speaking is WS-only. We need a proper websockets client to replay the transcript 
    # and listen for the `evaluation` event. For now, we mark this out of scope to prevent 
    # testing a fabricated bare-LLM system instead of the actual 4-agent swarm.
    print("Warning: Speaking Eval is WS-only and currently out of scope. Skipping.")
    return {"speaking_accuracy": None}

def run_writing_eval(data: dict) -> dict:
    passes = 0
    total = 0
    writing_url = os.environ.get("WRITING_SERVICE_URL", "http://localhost:8000")
    
    for item in data.get('writing', []):
        total += 1
        payload = {
            "userId": "eval_test_user",
            "essayText": item["essay"],
            "submissionType": "typed_text",
            "examType": "IELTS Writing"
        }
        try:
            response = httpx.post(f"{writing_url}/essays/evaluate", json=payload, timeout=30.0)
            service_data = response.json()
            if abs(service_data.get('overall_band', 0) - item.get("expected_band", 0)) <= 0.5:
                passes += 1
        except Exception:
            pass

    accuracy = (passes / total) if total > 0 else 0.0
    return {"writing_accuracy": accuracy}

def _calc_delta(current, prev):
    if current is None or prev is None:
        return None
    return current - prev

def main():
    parser = argparse.ArgumentParser(description="End-to-end evaluation suite")
    parser.add_argument("--compare-with", type=str, default=None)
    parser.add_argument("--s3-upload-path", type=str, default=None)
    args = parser.parse_args()

    dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    dataset = load_golden_dataset(dataset_path)
    if not dataset:
        sys.exit(1)

    prev_reports = {}
    if args.compare_with:
        prev_reports = load_previous_report(args.compare_with)

    metrics = {}
    metrics.update(run_rag_eval(dataset))
    metrics.update(run_scoring_eval(dataset))
    metrics.update(run_speaking_eval(dataset))
    metrics.update(run_writing_eval(dataset))

    prev_metrics = prev_reports.get("metrics", {})
    deltas = {
        "delta_rag": _calc_delta(metrics["rag_accuracy"], prev_metrics.get("rag_accuracy")),
        "delta_gate": _calc_delta(metrics["gate_accuracy"], prev_metrics.get("gate_accuracy")),
        "delta_scoring_mae": _calc_delta(metrics["scoring_mae"], prev_metrics.get("scoring_mae")),
        "delta_speaking": _calc_delta(metrics["speaking_accuracy"], prev_metrics.get("speaking_accuracy")),
        "delta_writing": _calc_delta(metrics["writing_accuracy"], prev_metrics.get("writing_accuracy"))
    }

    report = ReportSchema(
        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        metrics=ReportMetrics(**metrics),
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

    if args.s3_upload_path and args.s3_upload_path.startswith("s3://"):
        try:
            parsed = urlparse(args.s3_upload_path)
            bucket = parsed.netloc
            key = f"{parsed.path.lstrip('/')}/{filename}"
            s3_client = boto3.client('s3', endpoint_url=os.environ.get('AWS_ENDPOINT_URL'))
            s3_client.upload_file(report_path, bucket, key)
            print(f"Report uploaded to s3://{bucket}/{key}")
        except Exception as e:
            print(f"Failed to upload report to S3: {e}")

    # 1. Enforce Absolute Thresholds (skip Nones)
    if metrics["gate_accuracy"] is not None and metrics["gate_accuracy"] < 1.0:
        print("FAIL: Gate accuracy dropped below 100%.")
        sys.exit(1)
    if metrics["rag_accuracy"] is not None and metrics["rag_accuracy"] < 0.8:
        print("FAIL: RAG accuracy dropped below 80%.")
        sys.exit(1)
    if metrics["speaking_accuracy"] is not None and metrics["speaking_accuracy"] < 0.8:
        print("FAIL: Speaking accuracy dropped below 80%.")
        sys.exit(1)
    if metrics["writing_accuracy"] is not None and metrics["writing_accuracy"] < 0.8:
        print("FAIL: Writing accuracy dropped below 80%.")
        sys.exit(1)

    # 2. Enforce Regression Thresholds
    if (deltas["delta_rag"] is not None and deltas["delta_rag"] < -0.05) or \
       (deltas["delta_gate"] is not None and deltas["delta_gate"] < -0.05) or \
       (deltas["delta_speaking"] is not None and deltas["delta_speaking"] < -0.05) or \
       (deltas["delta_writing"] is not None and deltas["delta_writing"] < -0.05) or \
       (deltas["delta_scoring_mae"] is not None and deltas["delta_scoring_mae"] > 0.05):
        print("FAIL: A metric regressed by more than 5%.")
        sys.exit(1)

    print("PASS: All evaluations met targets.")
    sys.exit(0)

if __name__ == "__main__":
    main()