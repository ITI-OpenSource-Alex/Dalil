import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from evals.judge import JudgeVerdict
from evals.runner import compute_accuracy, compute_mae, check_regression_gate

def test_runner_reports_accuracy_and_mae_per_criterion():
    verdicts = [
        JudgeVerdict(
            item_id="w-01",
            verdict="ACCURATE",
            agent_band=6.5,
            expert_band=6.5,
            delta=0.0,
            reason="Good grounding",
            agent_criteria={"task_response": 6.5, "coherence": 6.5},
            expert_criteria={"task_response": 6.5, "coherence": 6.5}
        ),
        JudgeVerdict(
            item_id="w-02",
            verdict="ACCURATE",
            agent_band=7.0,
            expert_band=6.5,
            delta=0.5,
            reason="Grounding valid",
            agent_criteria={"task_response": 7.0, "coherence": 6.5},
            expert_criteria={"task_response": 6.5, "coherence": 6.5}
        )
    ]
    acc = compute_accuracy(verdicts)
    mae = compute_mae(verdicts, domain="writing")

    assert acc["accuracy"] == 1.0
    assert acc["judged"] == 2
    assert acc["accurate"] == 2

    assert mae["overall"] == 0.25
    assert "task_response" in mae["per_criterion"]
    assert mae["per_criterion"]["task_response"] == 0.25
    assert mae["per_criterion"]["coherence"] == 0.0

def test_accuracy_excludes_errored_items_from_denominator():
    verdicts = [
        JudgeVerdict(item_id="w-01", verdict="ACCURATE", agent_band=6.0, expert_band=6.0, delta=0.0, reason="ok"),
        JudgeVerdict(item_id="w-02", verdict="OVERSCORED", agent_band=8.0, expert_band=6.0, delta=2.0, reason="high"),
        JudgeVerdict(item_id="w-03", verdict="ERROR", agent_band=6.0, expert_band=6.0, delta=0.0, reason="", error="Timeout")
    ]
    acc = compute_accuracy(verdicts)
    assert acc["judged"] == 2
    assert acc["errored"] == 1
    assert acc["accurate"] == 1
    assert acc["accuracy"] == 0.5

def test_gate_fails_on_low_coverage():
    # 20 items total, only 1 judged and 19 errored (judged ratio 1/20 = 5% < 80%)
    current = {"writing": {"accuracy": 1.0, "accurate": 1, "judged": 1, "errored": 19}}
    passed, failures = check_regression_gate(current, previous=None)
    assert not passed
    assert any("COVERAGE" in f for f in failures)

def test_gate_fails_below_80_percent():
    current = {"writing": {"accuracy": 0.75, "accurate": 15, "judged": 20, "errored": 0}}
    passed, failures = check_regression_gate(current, previous=None)
    assert not passed
    assert any("FLOOR" in f for f in failures)

def test_gate_fails_on_more_than_5_point_drop():
    current = {"writing": {"accuracy": 0.79, "accurate": 79, "judged": 100, "errored": 0}}
    previous = {"writing": {"accuracy": 0.85}}
    passed, failures = check_regression_gate(current, previous)
    assert not passed
    assert any("REGRESSION" in f for f in failures)

def test_gate_passes_on_first_ever_run():
    current = {"writing": {"accuracy": 0.85, "accurate": 17, "judged": 20, "errored": 0}}
    passed, failures = check_regression_gate(current, previous=None)
    assert passed
    assert len(failures) == 0
