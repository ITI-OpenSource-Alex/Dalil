"""Emit the Python implementation's view of a speaking evaluation fixture.

Companion to services/speaking/cmd/contract-digest and emit_typescript.ts. The
digest format is defined in README.md next to this file; the three emitters must
produce byte-identical output for the same fixture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parents[1] / "py"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from contracts.speaking_evaluation import (  # noqa: E402
    CriterionResult,
    SpeakingEvaluation,
    round_ielts_band,
)


def _opt_float(value: float | None) -> str:
    """The distinction the whole harness exists to protect.

    ``absent`` and ``0.0000`` are different strings. An implementation that ever
    substitutes zero for "not measured" changes this line and fails the diff.
    """
    return "absent" if value is None else f"{value:.4f}"


def _opt_str(value: object) -> str:
    if value is None or value == "":
        return "absent"
    # Enum members render as their value, not "CriterionID.FLUENCY_COHERENCE".
    return getattr(value, "value", value)


def _join(items: list[str]) -> str:
    return ",".join(items) if items else "-"


def _criterion_lines(index: int, c: CriterionResult) -> list[str]:
    p = f"criterion[{index}]"
    return [
        f"{p}.criterion_id={_opt_str(c.criterion_id)}",
        f"{p}.status={_opt_str(c.status)}",
        f"{p}.band={_opt_float(c.band)}",
        f"{p}.unavailable_reason={_opt_str(c.unavailable_reason)}",
        f"{p}.rubric_match_ids={_join([m.descriptor_id for m in c.rubric_matches])}",
        f"{p}.evidence_kinds={_join([_opt_str(e.kind) for e in c.evidence])}",
        f"{p}.measurements={_join(list(c.measurements))}",
        f"{p}.limitations_count={len(c.limitations)}",
        f"{p}.improvement_actions_count={len(c.improvement_actions)}",
    ]


def digest(raw: bytes) -> list[str] | None:
    """Return the digest lines, or None if this implementation rejects."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"python: not valid JSON: {exc}", file=sys.stderr)
        return None

    try:
        # extra="forbid" on the models means an unknown field is a rejection, not
        # a silently dropped key. Drift should be loud.
        e = SpeakingEvaluation.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError, or a model_validator
        print(f"python: rejected: {exc}", file=sys.stderr)
        return None

    unresolved = e.unresolved_references()
    if unresolved:
        for problem in unresolved:
            print(f"python: {problem}", file=sys.stderr)
        return None

    lines = [
        "verdict=accepted",
        f"schema_version={e.schema_version}",
        f"evaluation_id={e.evaluation_id}",
        f"mode={_opt_str(e.mode)}",
        f"status={_opt_str(e.status)}",
        f"score_semantics={e.score_semantics}",
        f"criteria_count={len(e.criteria)}",
    ]

    scored: list[float] = []
    for i, c in enumerate(e.criteria):
        lines.extend(_criterion_lines(i, c))
        if c.scored and c.band is not None:
            scored.append(c.band)

    lines.extend(
        [
            f"scored_count={len(scored)}",
            f"min_criteria_required={e.overall.min_criteria_required}",
            f"overall.band={_opt_float(e.overall.band)}",
            f"overall.unrounded_mean={_opt_float(e.overall.unrounded_mean)}",
            f"overall.included={_join([_opt_str(c) for c in e.overall.included_criteria])}",
            f"overall.excluded={_join([_opt_str(c) for c in e.overall.excluded_criteria])}",
            f"overall.rounding_rule={e.overall.rounding_rule}",
        ]
    )

    # Recomputed here, not read off the fixture. This is what catches a rounding
    # rule that drifted in one language only.
    threshold_met = len(scored) >= e.overall.min_criteria_required
    lines.append(f"derived.threshold_met={'true' if threshold_met else 'false'}")
    if threshold_met and scored:
        mean = sum(scored) / len(scored)
        lines.append(f"derived.mean_of_scored={mean:.4f}")
        lines.append(f"derived.rounded_band={round_ielts_band(mean):.4f}")
    else:
        lines.append("derived.mean_of_scored=absent")
        lines.append("derived.rounded_band=absent")

    measurement_ids = sorted(m.id for m in e.provenance.measurements)
    lines.extend(
        [
            f"provenance.rubric_id={e.provenance.rubric_id}",
            f"provenance.rubric_version={e.provenance.rubric_version}",
            f"provenance.scorer_version={e.provenance.scorer_version}",
            f"provenance.llm_model={_opt_str(e.provenance.llm_model)}",
            f"provenance.audio_format={_opt_str(e.provenance.audio_format)}",
            f"provenance.measurement_ids={_join(measurement_ids)}",
        ]
    )

    if e.telemetry is None:
        lines.append("telemetry.present=false")
        lines.append("telemetry.cost_usd=absent")
    else:
        lines.append("telemetry.present=true")
        lines.append(f"telemetry.cost_usd={_opt_float(e.telemetry.cost_usd)}")

    lines.append("validation_problems=0")
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: emit_python.py <fixture.json>", file=sys.stderr)
        return 2

    try:
        raw = Path(sys.argv[1]).read_bytes()
    except OSError as exc:
        print(f"emit_python: {exc}", file=sys.stderr)
        return 2

    lines = digest(raw)
    # The verdict alone: where a payload was caught is an implementation detail,
    # whether it was caught is the contract.
    out = "\n".join(lines) + "\n" if lines is not None else "verdict=rejected\n"
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
