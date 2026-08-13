"""SPEAK-EVAL-009 — the required CI job must be able to go red.

The workflow this replaces set `STRICT_EVAL_MODE: "false"` and then
`continue-on-error: ${{ env.STRICT_EVAL_MODE != 'true' }}`, so the eval step
could not fail whatever broke. It reported success for months without ever
having been able to report anything else.

A gate that cannot fail is worse than no gate: the absence of a check is
visible, while a check that always passes reports safety it never verified. So
these tests assert the properties of the workflow files themselves, because
"is this job actually required" is not something the job can tell you about
itself at runtime.

The ticket's first acceptance criterion is that deliberately breaking the
speaking client makes required CI red. That is proved here in two halves: the
required workflow runs the speaking tests with no error suppression, and the
suite it runs genuinely fails when the client is broken (test_gladia_ingestion
and the contract tests both cover that).
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
PR_GATE = WORKFLOWS / "speaking-eval-pr.yml"
NIGHTLY = WORKFLOWS / "speaking-eval-nightly.yml"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def all_steps(workflow: dict):
    for job_name, job in workflow.get("jobs", {}).items():
        for step in job.get("steps", []) or []:
            yield job_name, step


# --- the required gate can fail ---------------------------------------------


def test_the_required_gate_suppresses_no_failures():
    workflow = load(PR_GATE)

    for name, job in workflow["jobs"].items():
        assert not job.get("continue-on-error"), f"job {name} cannot fail"

    for job_name, step in all_steps(workflow):
        assert not step.get("continue-on-error"), (
            f"{job_name}: step {step.get('name')!r} suppresses its own failure"
        )


def test_no_step_swallows_a_nonzero_exit():
    """`|| true` and a trailing `exit 0` are continue-on-error by other means."""
    text = PR_GATE.read_text(encoding="utf-8")

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "|| true" not in stripped, f"failure swallowed: {stripped}"
        assert not stripped.endswith("exit 0"), f"failure swallowed: {stripped}"


def test_the_required_gate_actually_runs_the_speaking_tests():
    # A gate that suppresses nothing but tests nothing is equally green.
    text = PR_GATE.read_text(encoding="utf-8")

    assert "go test -race ./..." in text, "the speaking suite is not run"
    assert "run_conformance.py" in text, "contract conformance is not run"
    assert "manifest/validate.py" in text, "dataset governance is not run"


def test_the_required_gate_makes_no_paid_provider_calls():
    """Acceptance: PR CI makes no unexpected external calls."""
    workflow = load(PR_GATE)

    # Comment lines are dropped before checking: this file explains WHY the key
    # is absent, and a naive substring search matches its own explanation.
    live = "\n".join(
        line
        for line in PR_GATE.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )

    # No provider credential reaches the PR gate at all, so a regression that
    # started calling out has nothing to call with.
    assert "GLADIA_API_KEY" not in live, "the PR gate should not receive a provider key"
    assert "secrets." not in live, "the PR gate should not receive any secret"

    for _, step in all_steps(workflow):
        env = step.get("env", {}) or {}
        allow = env.get("SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS")
        if allow is not None:
            assert str(allow).lower() == "false", "live providers enabled in PR CI"


# --- the nightly reports a missing secret as a failure ----------------------


def test_a_missing_required_secret_is_a_failure_not_a_skip():
    """A green run that measured nothing is the outcome this prevents."""
    workflow = load(NIGHTLY)
    preflight = workflow["jobs"]["preflight"]

    body = " ".join(
        str(step.get("run", "")) for step in preflight.get("steps", [])
    )
    assert "exit 1" in body, "a missing secret does not fail the run"
    assert "::error::" in body, "a missing secret is not surfaced as an error"

    # `if: ...` on the job would turn it into a skip, which reports success.
    assert "if" not in preflight, "preflight is conditional, so it can be skipped"


def test_lanes_wait_on_the_exact_dependency_not_always():
    workflow = load(NIGHTLY)
    lane = workflow["jobs"]["scorer-lane"]

    assert lane.get("needs") == "preflight"
    condition = str(lane.get("if", ""))
    assert "preflight.outputs.ready" in condition, (
        "the lane does not wait on preflight's result"
    )
    assert "always()" not in condition, (
        "a lane running after a failed preflight produces numbers nobody should read"
    )


# --- a failed candidate cannot become the baseline --------------------------


def test_promotion_requires_success():
    workflow = load(NIGHTLY)
    promote = workflow["jobs"]["promote-baseline"]

    condition = str(promote.get("if", ""))
    assert "success()" in condition, "a failed run can replace the baseline"
    assert "always()" not in condition
    assert promote.get("needs") == "scorer-lane"


def test_promotion_checks_the_candidate_before_publishing():
    """A baseline with no provenance poisons every comparison after it."""
    workflow = load(NIGHTLY)
    promote = workflow["jobs"]["promote-baseline"]

    body = " ".join(str(step.get("run", "")) for step in promote.get("steps", []))
    for required in ("run_id", "git_sha", "speaking_lanes"):
        assert required in body, f"promotion does not verify {required}"
    assert "refusing to promote" in body


def test_promotion_keeps_a_named_predecessor():
    """Durable: a bad promotion is rolled back to a run, not lost."""
    body = NIGHTLY.read_text(encoding="utf-8")

    assert "runs/${{ github.run_id }}.json" in body, (
        "only `latest` is written, so a bad promotion cannot be rolled back"
    )
    assert "latest_report.json" in body


def test_promotion_fails_loudly_when_storage_is_unconfigured():
    body = NIGHTLY.read_text(encoding="utf-8")
    assert "refusing to promote silently" in body


# --- artifacts carry transcript excerpts ------------------------------------


def test_report_artifacts_have_bounded_retention():
    """A report quotes a candidate's speech. It should not sit forever."""
    workflow = load(NIGHTLY)

    for job_name, step in all_steps(workflow):
        if str(step.get("uses", "")).startswith("actions/upload-artifact"):
            retention = (step.get("with") or {}).get("retention-days")
            assert retention, f"{job_name}: artifact has unbounded retention"
            assert int(retention) <= 90
