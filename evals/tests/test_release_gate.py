"""SPEAK-EVAL-010 — the release gate.

Acceptance:

  - thresholds have recorded empirical rationale;
  - both absolute and non-regression conditions are enforced;
  - threshold changes are reviewable and cannot be made inside a candidate run;
  - known degradation is caught.

The first criterion is currently met by REFUSING to release rather than by
having rationale: no item in the dataset has two independent human ratings, so
human-human agreement has never been measured, and section 11.4 forbids
carrying forward numbers that were not derived from it. The gate abstains, and
these tests pin that it abstains rather than quietly passing.

The fourth is a rehearsal: a deliberately degraded scorer is run through the
gate under an approved policy and must be caught. A gate nobody has watched fail
is a gate nobody knows works.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from evals.speaking.policy.gate import (  # noqa: E402
    DEFAULT_POLICY,
    GateResult,
    Verdict,
    evaluate,
    load_policy,
)


# A policy with real values, used ONLY to rehearse enforcement. It is built here
# rather than committed, so nothing can mistake it for an approved policy.
def approved_policy() -> dict:
    return {
        "policy_version": "test-policy/v1",
        "approved": True,
        "absolute": {
            "min_within_half_band": {"value": 0.70},
            "max_mae": {"value": 0.75},
            "max_abs_bias": {"value": 0.50},
            "min_coverage": {"value": 0.95},
        },
        "non_regression": {
            "max_mae_increase": {"value": 0.25},
            "max_within_half_band_drop": {"value": 0.05},
        },
        "slices": {"min_items_per_slice": 20},
        "bias_escalation": {
            "max_slice_bias_delta": 0.5,
            "escalate_to": "assessment lead",
        },
        "sample_size": {
            "min_items_for_any_verdict": 30,
            "min_items_for_regression_verdict": 50,
        },
    }


def good_candidate(**overrides) -> dict:
    candidate = {
        "n": 60,
        "within_half_band": 0.82,
        "mae": 0.42,
        "bias": -0.10,
        "coverage": 1.0,
    }
    candidate.update(overrides)
    return candidate


# --- the shipped policy refuses to gate -------------------------------------


def test_the_shipped_policy_is_unapproved_and_abstains():
    result = evaluate(good_candidate(), policy=load_policy())

    assert result.verdict is Verdict.ABSTAIN
    assert not result.released
    assert "not approved" in " ".join(result.reasons)


def test_abstain_is_not_a_pass():
    """The distinction the whole module rests on. ABSTAIN must never release."""
    result = GateResult(verdict=Verdict.ABSTAIN, policy_version="x")
    assert not result.released

    assert not evaluate(good_candidate(), policy=load_policy()).released


def test_the_shipped_policy_records_why_it_is_unapproved():
    policy = load_policy()

    assert policy["approved"] is False
    explanation = " ".join(policy["why_unapproved"])
    assert "human-human agreement" in explanation
    assert "double-rated" in explanation


def test_provisional_suggestions_are_never_used_as_values():
    """The suggestions exist to inform whoever sets the value.

    Treating one as a fallback would make the gate enforce exactly the
    unratified numbers the policy says it must not.
    """
    policy = load_policy()
    policy["approved"] = True  # approve it WITHOUT setting any value

    result = evaluate(good_candidate(), policy=policy)

    assert result.checks_run == 0
    assert result.verdict is Verdict.ABSTAIN
    assert "zero checks" in " ".join(result.reasons)


# --- a threshold cannot be set from inside a run ----------------------------


def test_the_gate_does_not_mutate_the_policy_it_was_given():
    policy = approved_policy()
    before = copy.deepcopy(policy)

    evaluate(good_candidate(), policy=policy)

    assert policy == before, "the gate altered the policy it was measured against"


def test_the_gate_does_not_mutate_the_candidate():
    candidate = good_candidate()
    before = copy.deepcopy(candidate)

    evaluate(candidate, policy=approved_policy())

    assert candidate == before


def test_no_environment_override_exists(monkeypatch):
    """A candidate that could choose its own bar is not being measured."""
    for name in (
        "SPEAKING_MAX_MAE",
        "SPEAKING_GATE_THRESHOLD",
        "SPEAKING_RELEASE_POLICY",
        "GOA_GATE_OVERRIDE",
    ):
        monkeypatch.setenv(name, "9999")

    failing = good_candidate(mae=5.0)
    result = evaluate(failing, policy=approved_policy())

    assert result.verdict is Verdict.FAIL, "an env var influenced the gate"


def test_changing_a_threshold_means_editing_a_reviewable_file():
    # The policy is data on disk, not code. This is what makes a threshold
    # change show up as a diff with an author.
    assert DEFAULT_POLICY.exists()
    assert DEFAULT_POLICY.suffix == ".json"
    json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))


# --- sample size ------------------------------------------------------------


def test_the_gate_abstains_below_a_usable_sample_size():
    result = evaluate(good_candidate(n=3), policy=approved_policy())

    assert result.verdict is Verdict.ABSTAIN
    assert "below the 30" in " ".join(result.reasons)


def test_regression_is_skipped_but_absolutes_still_apply_at_mid_sample():
    candidate = good_candidate(n=40)
    baseline = good_candidate(n=40, mae=0.20)

    result = evaluate(candidate, baseline=baseline, policy=approved_policy())

    assert result.verdict is Verdict.PASS
    assert any("non-regression" in s for s in result.checks_skipped)


# --- absolute conditions ----------------------------------------------------


def test_a_good_candidate_passes():
    result = evaluate(good_candidate(), policy=approved_policy())

    assert result.verdict is Verdict.PASS
    assert result.checks_run == 4


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"within_half_band": 0.55}, "below the floor"),
        ({"mae": 1.20}, "exceeds the ceiling"),
        ({"bias": -1.30}, "exceeds the permitted magnitude"),
        ({"coverage": 0.60}, "coverage"),
    ],
)
def test_each_absolute_condition_is_enforced(override, fragment):
    result = evaluate(good_candidate(**override), policy=approved_policy())

    assert result.verdict is Verdict.FAIL
    assert fragment in " ".join(result.reasons)


def test_bias_is_judged_on_magnitude_not_sign():
    # A scorer a band generous is as unusable as one a band harsh.
    generous = evaluate(good_candidate(bias=+1.2), policy=approved_policy())
    harsh = evaluate(good_candidate(bias=-1.2), policy=approved_policy())

    assert generous.verdict is Verdict.FAIL
    assert harsh.verdict is Verdict.FAIL


# --- non-regression ---------------------------------------------------------


def test_a_regression_fails_even_when_absolutes_are_met():
    # The candidate is inside every floor and still materially worse than what
    # is deployed. Absolute conditions alone would have released it.
    baseline = good_candidate(mae=0.30, within_half_band=0.90)
    candidate = good_candidate(mae=0.70, within_half_band=0.86)

    result = evaluate(candidate, baseline=baseline, policy=approved_policy())

    assert result.verdict is Verdict.FAIL
    assert "regressed" in " ".join(result.reasons)


def test_an_agreement_drop_is_caught_separately_from_mae():
    baseline = good_candidate(within_half_band=0.90)
    candidate = good_candidate(within_half_band=0.80)

    result = evaluate(candidate, baseline=baseline, policy=approved_policy())

    assert result.verdict is Verdict.FAIL
    assert "dropped" in " ".join(result.reasons)


def test_an_improvement_is_not_a_regression():
    baseline = good_candidate(mae=0.70)
    candidate = good_candidate(mae=0.35)

    assert evaluate(candidate, baseline=baseline, policy=approved_policy()).verdict is Verdict.PASS


# --- the degradation rehearsal ----------------------------------------------


DEGRADATIONS = {
    "scorer returns a constant band": dict(
        within_half_band=0.31, mae=1.40, bias=-1.40, coverage=1.0
    ),
    "scorer is a full band generous": dict(
        within_half_band=0.40, mae=1.05, bias=1.05, coverage=1.0
    ),
    "half the agents time out": dict(
        within_half_band=0.78, mae=0.50, bias=-0.20, coverage=0.50
    ),
    "max_tokens starves every agent": dict(
        within_half_band=0.0, mae=2.10, bias=-2.10, coverage=0.02
    ),
    "pronunciation returns band 0 for want of prosody": dict(
        within_half_band=0.45, mae=1.15, bias=-1.15, coverage=1.0
    ),
}


@pytest.mark.parametrize("name, metrics", sorted(DEGRADATIONS.items()))
def test_known_degradation_is_caught(name, metrics):
    """Every one of these is a defect this project actually shipped.

    A gate nobody has watched fail is a gate nobody knows works, so each real
    failure mode is rehearsed against an approved policy.
    """
    result = evaluate(good_candidate(**metrics), policy=approved_policy())

    assert result.verdict is Verdict.FAIL, f"{name} was not caught"
    assert result.reasons


def test_the_rehearsal_covers_the_defects_this_project_hit():
    # Named so a future reader can see the rehearsal is grounded in history
    # rather than in imagination.
    joined = " ".join(DEGRADATIONS)
    assert "max_tokens" in joined
    assert "pronunciation" in joined
    assert "time out" in joined


# --- bias escalation --------------------------------------------------------


def test_a_biased_slice_escalates_without_failing_the_build():
    candidate = good_candidate(
        slices={"band_9": {"n": 25, "bias": -0.95}, "band_6": {"n": 30, "bias": -0.05}}
    )

    result = evaluate(candidate, policy=approved_policy())

    assert result.verdict is Verdict.PASS
    assert len(result.escalations) == 1
    assert "band_9" in result.escalations[0]
    assert "assessment lead" in result.escalations[0]


def test_a_slice_below_the_minimum_size_does_not_escalate():
    """A bias figure over eight items is noise, and escalating on it trains
    people to ignore escalations."""
    candidate = good_candidate(slices={"band_9": {"n": 8, "bias": -2.0}})

    result = evaluate(candidate, policy=approved_policy())

    assert result.escalations == []
