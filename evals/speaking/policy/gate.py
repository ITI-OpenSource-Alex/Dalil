"""Release gate for the speaking scorer (SPEAK-EVAL-010).

Decides whether a candidate run may be released, against a versioned policy that
lives in a file and changes by review.

Three properties shape this module, and each exists because the obvious
alternative is worse.

**It fails closed on an unapproved policy.** The thresholds in
release_policy.json are provisional and carry no empirical rationale, because
human-human agreement has never been measured on this dataset. A gate that
enforced them would produce a release decision that looks like evidence and is
not. So an unapproved policy yields ABSTAIN -- neither pass nor fail -- and the
caller is told why.

**A threshold cannot be set from inside a run.** `evaluate()` takes the policy
as data and never reads the environment, never accepts an override argument, and
never mutates what it was given. A candidate that could choose the bar it is
measured against is not being measured. The only way to change a threshold is to
edit the policy file, which is a reviewable diff with an author.

**It abstains below a sample size that can support a verdict.** n=3 cannot
distinguish a good scorer from a bad one, and a gate that returns PASS on three
items has told you nothing while sounding certain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_POLICY = HERE / "release_policy.json"


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    #: Not "pass with caveats". The gate could not reach a decision, and saying
    #: so is different from saying the candidate is acceptable.
    ABSTAIN = "abstain"


@dataclass
class GateResult:
    verdict: Verdict
    policy_version: str
    reasons: list[str] = field(default_factory=list)
    escalations: list[str] = field(default_factory=list)
    checks_run: int = 0
    checks_skipped: list[str] = field(default_factory=list)

    @property
    def released(self) -> bool:
        """Only PASS releases. ABSTAIN deliberately does not."""
        return self.verdict is Verdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "policy_version": self.policy_version,
            "reasons": self.reasons,
            "escalations": self.escalations,
            "checks_run": self.checks_run,
            "checks_skipped": self.checks_skipped,
        }


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _threshold(section: dict[str, Any], name: str) -> float | None:
    """Read a threshold, or None when it has not been set.

    `provisional_suggestion` is deliberately NOT consulted. It exists to inform
    whoever eventually sets the value; treating it as a fallback would make the
    gate enforce exactly the unratified numbers the policy says it must not.
    """
    entry = section.get(name)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return float(value) if isinstance(value, (int, float)) else None


def evaluate(
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> GateResult:
    """Decide whether `candidate` may be released.

    `candidate` and `baseline` are metric dicts: n, mae, bias, within_half_band,
    coverage, and optionally slices. Both are read-only.
    """
    policy = policy if policy is not None else load_policy()
    version = str(policy.get("policy_version", "unknown"))

    result = GateResult(verdict=Verdict.ABSTAIN, policy_version=version)

    # 1. An unapproved policy cannot gate anything.
    if not policy.get("approved"):
        result.reasons.append(
            f"Policy {version} is not approved, so no release decision was made. "
            f"Its thresholds are provisional and carry no empirical rationale: "
            f"human-human agreement has not been measured on this dataset. "
            f"Enforcing them would produce a decision that looks like evidence."
        )
        return result

    # 2. Too few items to support any verdict.
    sample = policy.get("sample_size", {})
    minimum = sample.get("min_items_for_any_verdict")
    n = candidate.get("n")
    if not isinstance(n, int):
        result.reasons.append("Candidate reports no item count; cannot gate.")
        return result
    if isinstance(minimum, int) and n < minimum:
        result.reasons.append(
            f"{n} items is below the {minimum} needed for any verdict. A gate that "
            f"passes on this many has told you nothing while sounding certain."
        )
        return result

    failures: list[str] = []
    absolute = policy.get("absolute", {})

    def check(name: str, actual: float | None, compare, describe: str) -> None:
        limit = _threshold(absolute, name)
        if limit is None:
            result.checks_skipped.append(f"{name} (no approved value)")
            return
        if actual is None:
            result.checks_skipped.append(f"{name} (candidate did not report it)")
            return
        result.checks_run += 1
        if not compare(actual, limit):
            failures.append(describe.format(actual=actual, limit=limit))

    check(
        "min_within_half_band", candidate.get("within_half_band"),
        lambda a, l: a >= l,
        "within-0.5-band agreement {actual:.3f} is below the floor of {limit:.3f}",
    )
    check(
        "max_mae", candidate.get("mae"),
        lambda a, l: a <= l,
        "MAE {actual:.3f} exceeds the ceiling of {limit:.3f}",
    )
    check(
        "max_abs_bias", candidate.get("bias"),
        lambda a, l: abs(a) <= l,
        "bias {actual:+.3f} exceeds the permitted magnitude of {limit:.3f}",
    )
    check(
        "min_coverage", candidate.get("coverage"),
        lambda a, l: a >= l,
        "coverage {actual:.3f} is below the floor of {limit:.3f}",
    )

    # 3. Non-regression, only when there is a baseline to regress against.
    regression = policy.get("non_regression", {})
    if baseline:
        min_for_regression = sample.get("min_items_for_regression_verdict")
        if isinstance(min_for_regression, int) and n < min_for_regression:
            result.checks_skipped.append(
                f"non-regression ({n} items, needs {min_for_regression})"
            )
        else:
            mae_limit = _threshold(regression, "max_mae_increase")
            if mae_limit is not None and _both_present(candidate, baseline, "mae"):
                result.checks_run += 1
                delta = candidate["mae"] - baseline["mae"]
                if delta > mae_limit:
                    failures.append(
                        f"MAE regressed by {delta:+.3f} against the baseline, above "
                        f"the permitted {mae_limit:.3f}"
                    )

            agreement_limit = _threshold(regression, "max_within_half_band_drop")
            if agreement_limit is not None and _both_present(
                candidate, baseline, "within_half_band"
            ):
                result.checks_run += 1
                drop = baseline["within_half_band"] - candidate["within_half_band"]
                if drop > agreement_limit:
                    failures.append(
                        f"within-0.5-band agreement dropped by {drop:.3f}, above the "
                        f"permitted {agreement_limit:.3f}"
                    )
    else:
        result.checks_skipped.append("non-regression (no baseline)")

    # 4. Bias by slice escalates to a person rather than failing the build.
    result.escalations.extend(_slice_escalations(candidate, policy))

    if result.checks_run == 0:
        result.reasons.append(
            "No threshold in the approved policy had a value set, so nothing was "
            "checked. A gate that ran zero checks must not report a pass."
        )
        return result

    if failures:
        result.verdict = Verdict.FAIL
        result.reasons = failures
        return result

    result.verdict = Verdict.PASS
    result.reasons.append(
        f"{result.checks_run} check(s) passed under policy {version}."
    )
    return result


def _both_present(a: dict, b: dict, key: str) -> bool:
    return isinstance(a.get(key), (int, float)) and isinstance(b.get(key), (int, float))


def _slice_escalations(candidate: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Flag slices whose bias differs materially from the whole.

    Suppressed below the minimum slice size: a bias figure over eight items is
    noise, and escalating on it trains people to ignore escalations.
    """
    config = policy.get("bias_escalation", {})
    limit = config.get("max_slice_bias_delta")
    if not isinstance(limit, (int, float)):
        return []

    slices = candidate.get("slices")
    if not isinstance(slices, dict):
        return []

    minimum = policy.get("slices", {}).get("min_items_per_slice", 0)
    overall = candidate.get("bias")
    if not isinstance(overall, (int, float)):
        return []

    out = []
    for name, stats in sorted(slices.items()):
        if not isinstance(stats, dict):
            continue
        n = stats.get("n")
        bias = stats.get("bias")
        if not isinstance(n, int) or not isinstance(bias, (int, float)):
            continue
        if n < minimum:
            continue
        delta = abs(bias - overall)
        if delta > limit:
            out.append(
                f"slice {name!r} (n={n}) has bias {bias:+.3f} against {overall:+.3f} "
                f"overall, a difference of {delta:.3f}. Escalate to "
                f"{config.get('escalate_to', 'the assessment lead')}."
            )
    return out
