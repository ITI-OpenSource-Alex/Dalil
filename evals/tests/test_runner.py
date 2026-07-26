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


# --- Guards for the defects the first live run exposed. Every one of these passed
# --- its unit tests before the run and still produced a meaningless number, because
# --- nothing exercised the seam between the service response and the judge.

from evals.judge import judge_evaluation
from evals.runner import _normalise_agent_result, SERVICE_TO_EVAL_CRITERION


def test_service_criterion_names_are_translated_to_eval_names():
    """The service says cohesion/vocabulary; the rubric and dataset say
    coherence/lexical. Untranslated, per-criterion MAE averages an empty set and
    reports {} — a metric that renders as present and measures nothing."""
    body = {
        "overall_band": 6.5,
        "evaluations": [
            {"criterion": "task_response", "band_score": 6.0},
            {"criterion": "cohesion", "band_score": 7.0},
            {"criterion": "vocabulary", "band_score": 6.5},
            {"criterion": "grammar", "band_score": 6.5},
        ],
    }
    criteria = _normalise_agent_result(body)["criteria"]
    assert set(criteria) == {"task_response", "coherence", "lexical", "grammar"}
    assert criteria["coherence"] == 7.0
    assert criteria["lexical"] == 6.5


def test_every_service_criterion_has_an_eval_name():
    """A criterion added to the service must not silently vanish from MAE."""
    from evals.judge import CRITERIA
    assert set(SERVICE_TO_EVAL_CRITERION.values()) == set(CRITERIA["writing"])


def test_failed_agent_call_is_an_error_not_a_band_of_zero():
    """The bug that made a dead port look like 0% agent accuracy: a failed call was
    recorded as overall_band 0.0, so every item came back confidently UNDERSCORED
    against a band the agent never produced."""
    verdict = judge_evaluation(
        "writing",
        {"id": "w-01", "expected_band": 7.0, "essay": "text"},
        {"agent_error": "ConnectError: connection refused"},
    )
    assert verdict.is_error
    assert verdict.verdict == "ERROR"
    assert "connection refused" in verdict.error


def test_errored_agent_call_costs_no_judge_tokens():
    """There is nothing to grade, so the judge must not be invoked."""
    class ExplodingClient:
        def __getattr__(self, name):
            raise AssertionError("judge was called for an errored agent result")

    verdict = judge_evaluation(
        "writing",
        {"id": "w-01", "expected_band": 7.0, "essay": "text"},
        {"agent_error": "boom"},
        client=ExplodingClient(),
    )
    assert verdict.input_tokens == 0 and verdict.output_tokens == 0


def test_gate_ignores_metric_keys_that_are_not_domains():
    """`writing_mae` is a metrics key, not a domain. Walking the whole metrics dict
    turned it into a phantom failing domain: 'COVERAGE: writing_mae produced no
    judged items at all' on a run whose writing domain was fine."""
    healthy = {"writing": {"accuracy": 1.0, "judged": 3, "errored": 0, "accurate": 3}}
    passed, failures = check_regression_gate(healthy, None)
    assert passed, failures


def test_floor_and_regression_failures_are_distinct_messages():
    """DoD: the gate must distinguish 'below target' from 'fell since last run'."""
    current = {"writing": {"accuracy": 0.70, "judged": 10, "errored": 0, "accurate": 7}}
    previous = {"writing": {"accuracy": 0.95}}
    passed, failures = check_regression_gate(current, previous)
    assert not passed
    joined = " | ".join(failures)
    assert "FLOOR:" in joined
    assert "REGRESSION:" in joined


def test_absent_per_criterion_mae_states_why():
    """{} must not be readable as 'compared and agreed'."""
    verdicts = [
        JudgeVerdict(item_id="w-01", verdict="ACCURATE", agent_band=5.5,
                     expert_band=5.5, delta=0.0, reason="r",
                     agent_criteria={"task_response": 5.5}, expert_criteria={}),
    ]
    mae = compute_mae(verdicts, domain="writing")
    assert mae["per_criterion"] == {}
    assert "publish only an overall band" in mae["per_criterion_unavailable_reason"]
    assert mae["rows_with_expert_criteria"] == 0


# --- CI publishing. Both of these were "wired" in the workflow and did nothing.

from evals.runner import format_pr_comment, upload_report


def test_pr_comment_reports_gate_result_and_sample_size():
    body = format_pr_comment(
        {"writing": {"accuracy": 0.333, "judged": 3, "errored": 0, "accurate": 1}},
        {"writing": {"overall": 0.667}},
        ["FLOOR: writing accuracy 33.3% is below the 80% target (1/3)"],
        False,
    )
    assert "**Gate: FAIL**" in body
    assert "33.3%" in body
    # A percentage without its n invites a 3-item run to be read as a rate.
    assert "n = 3" in body
    assert "FLOOR:" in body


def test_pr_comment_says_when_nothing_was_measured():
    body = format_pr_comment({}, {}, [], True)
    assert "_none measured_" in body
    assert "**Gate: PASS**" in body


def test_upload_refreshes_latest_report_so_compare_with_has_a_target(tmp_path, mocker):
    """CI compares against latest_report.json. If the upload does not write that
    key, --compare-with finds nothing forever and the regression gate never fires."""
    report = tmp_path / "2026-01-01T000000Z.json"
    report.write_text('{"metrics": {}}', encoding="utf-8")

    client = mocker.Mock()
    mocker.patch("boto3.client", return_value=client)

    assert upload_report(str(report), "s3://goa-eval-reports/") is True
    written_keys = {call.kwargs["Key"] for call in client.put_object.call_args_list}
    assert "latest_report.json" in written_keys
    assert "2026-01-01T000000Z.json" in written_keys


def test_upload_failure_does_not_fail_the_run(tmp_path, mocker):
    report = tmp_path / "r.json"
    report.write_text("{}", encoding="utf-8")
    mocker.patch("boto3.client", side_effect=RuntimeError("no credentials"))
    assert upload_report(str(report), "s3://bucket/") is False
