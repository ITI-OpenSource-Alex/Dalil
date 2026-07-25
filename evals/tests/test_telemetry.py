import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from evals.telemetry import format_pr_comment, export_prometheus_metrics

def test_pr_comment_body_contains_domain_accuracy_target_delta_badge():
    metrics = {"writing_accuracy": 0.85, "speaking_accuracy": None}
    deltas = {"delta_writing": 0.02, "delta_speaking": None}
    failures = []

    comment = format_pr_comment(metrics, deltas, failures)
    assert "GOA Evaluation Pipeline Results" in comment
    assert "WRITING" in comment
    assert "85.0%" in comment
    assert "+2.0%" in comment
    assert "✅ PASS" in comment
    assert "UNMEASURED" in comment

def test_pr_comment_shows_failing_badge():
    metrics = {"writing_accuracy": 0.70}
    deltas = {"delta_writing": -0.06}
    failures = ["FLOOR: writing accuracy 70.0% is below 80%"]

    comment = format_pr_comment(metrics, deltas, failures)
    assert "![FAIL]" in comment
    assert "❌ FAIL" in comment
    assert "FLOOR: writing accuracy 70.0% is below 80%" in comment

def test_prometheus_gauge_labels():
    accuracy_stats = {"accuracy": 0.85}
    mae_stats = {"per_criterion": {"task_response": 0.25}}
    export_prometheus_metrics("writing", accuracy_stats, mae_stats)
