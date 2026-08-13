"""The four speaking evaluation lanes (SPEAK-EVAL-007).

The speaking eval has never produced a number. `run_speaking_eval` returned
`None` with a hardcoded sentence, and the reason it gave was honest: the rows
were synthetic transcripts with no audio, and the production path needs audio.

This module replaces that with four lanes, each exercising a different amount of
the real system. The point of splitting them is attribution. A single end-to-end
number tells you the speaking service is wrong; it does not tell you whether the
fault is in transcription, in prosody extraction, in the scorer, or in the
WebSocket transport. Four lanes that share a dataset and differ only in how much
of the stack they traverse localise the fault by construction.

    SCORER_ONLY   transcript -> swarm. No audio, no transport.
                  Measures the LLM scoring core against a human band.
    GOA_AUDIO     audio -> speech sidecar -> swarm. Adds transcription and
                  prosody, still no transport.
    PRACTICE_E2E  audio -> real WebSocket -> speaking service. The whole
                  practice path, binary frames and all.
    EXAM          audio -> holistic exam endpoint. The path services/exam uses.

Each lane declares the inputs it needs. An item that provides only a transcript
is eligible for SCORER_ONLY and for nothing else -- not because of a
bureaucratic rule, but because there is no audio to send. What this prevents is
the report claiming the audio pipeline was validated on evidence that never
touched it, which is the reporting-layer version of the defect SPEAK-EVAL-002
fixed in the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Lane(str, Enum):
    SCORER_ONLY = "scorer_only"
    GOA_AUDIO = "goa_audio"
    PRACTICE_E2E = "practice_e2e"
    EXAM = "exam"


class Outcome(str, Enum):
    """What happened to one item in one lane.

    `NOT_RUN` is separate from `FAILED` on purpose. An item the lane could never
    have accepted is not a failure of the system under test, and collapsing the
    two would make a dataset with no audio look like a broken pipeline. The
    reconciliation check depends on the distinction.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class LaneSpec:
    lane: Lane
    requires: frozenset[str]
    description: str
    exercises: tuple[str, ...]
    """Which parts of the stack this lane actually traverses. Printed beside
    every result, so a reader can see what a number does and does not cover."""


LANE_SPECS: dict[Lane, LaneSpec] = {
    Lane.SCORER_ONLY: LaneSpec(
        lane=Lane.SCORER_ONLY,
        requires=frozenset({"transcript"}),
        description="Transcript straight into the evaluation swarm.",
        exercises=("prompt", "rubric", "swarm", "aggregation"),
    ),
    Lane.GOA_AUDIO: LaneSpec(
        lane=Lane.GOA_AUDIO,
        requires=frozenset({"audio"}),
        description="Audio through the speech sidecar, then the swarm.",
        exercises=("stt", "prosody", "prompt", "rubric", "swarm", "aggregation"),
    ),
    Lane.PRACTICE_E2E: LaneSpec(
        lane=Lane.PRACTICE_E2E,
        requires=frozenset({"audio"}),
        description="Audio over the real practice WebSocket, as a browser sends it.",
        exercises=(
            "websocket", "audio_format", "stt", "prosody",
            "prompt", "rubric", "swarm", "aggregation",
        ),
    ),
    Lane.EXAM: LaneSpec(
        lane=Lane.EXAM,
        requires=frozenset({"audio"}),
        description="Audio through the holistic exam path used by services/exam.",
        exercises=("exam_api", "stt", "prosody", "prompt", "rubric", "holistic_swarm", "aggregation"),
    ),
}


def lanes_for(item: dict) -> list[Lane]:
    """Which lanes this item can feed, from what it declares it provides."""
    provided = set(item.get("inputs") or [])
    return [
        spec.lane
        for spec in LANE_SPECS.values()
        if spec.requires <= provided
    ]


def eligible_items(manifest: dict, lane: Lane, *, gating_only: bool = True) -> list[dict]:
    """Items a lane may consume.

    `gating_only` defaults to True because the caller that matters is the one
    about to publish a number. An exploratory run passes False and must label
    its output accordingly.
    """
    from evals.speaking.manifest.validate import gating_items

    pool = gating_items(manifest) if gating_only else manifest.get("items", [])
    return [item for item in pool if lane in lanes_for(item)]


@dataclass
class ItemResult:
    """One item, one lane. The unit the metrics are computed over."""

    item_id: str
    lane: Lane
    outcome: Outcome

    predicted_overall: float | None = None
    reference_overall: float | None = None

    predicted_criteria: dict[str, float] = field(default_factory=dict)
    reference_criteria: dict[str, float] = field(default_factory=dict)
    unavailable_criteria: dict[str, str] = field(default_factory=dict)

    reason: str | None = None
    latency_ms: int | None = None

    # Provenance, carried per item rather than per run. Two items in one run can
    # legitimately differ -- a re-ingested source, a different model on retry --
    # and a run-level field would quietly report one of them for both.
    manifest_item: dict = field(default_factory=dict)
    scorer_version: str | None = None
    llm_model: str | None = None

    @property
    def scored(self) -> bool:
        """Whether this item contributes to an accuracy figure.

        A prediction without a reference is not a data point; neither is a
        reference the system never produced an answer for. Both are counted
        separately in the reconciliation.
        """
        return (
            self.outcome in {Outcome.COMPLETE, Outcome.PARTIAL}
            and self.predicted_overall is not None
            and self.reference_overall is not None
        )

    @property
    def error(self) -> float | None:
        if not self.scored:
            return None
        return self.predicted_overall - self.reference_overall


def reconcile(results: list[ItemResult], expected_total: int) -> list[str]:
    """Check every item is accounted for.

    The ticket asks that all item counts reconcile. This is the check that makes
    a silently dropped item impossible to miss: if scored + unscored + not-run
    does not equal what the lane was handed, some item vanished between the
    manifest and the report, and the accuracy figure is computed over an unknown
    denominator.
    """
    problems: list[str] = []

    scored = sum(1 for r in results if r.scored)
    not_run = sum(1 for r in results if r.outcome is Outcome.NOT_RUN)
    failed = sum(1 for r in results if r.outcome is Outcome.FAILED)
    unscored = len(results) - scored - not_run - failed

    if len(results) != expected_total:
        problems.append(
            f"{len(results)} results for {expected_total} eligible items; "
            f"{abs(expected_total - len(results))} item(s) unaccounted for"
        )

    for result in results:
        if result.outcome is Outcome.NOT_RUN and not result.reason:
            problems.append(f"{result.item_id}: not run, with no reason recorded")
        if result.outcome is Outcome.FAILED and not result.reason:
            problems.append(f"{result.item_id}: failed, with no reason recorded")
        # The defect this whole project keeps meeting: a failure rendered as a
        # number. A failed item must not carry a band.
        if result.outcome in {Outcome.FAILED, Outcome.NOT_RUN} and result.predicted_overall is not None:
            problems.append(
                f"{result.item_id}: outcome is {result.outcome.value} but it carries a "
                f"band of {result.predicted_overall}; a failure must stay a failure"
            )

    if scored + not_run + failed + unscored != len(results):
        problems.append("internal: outcome partition does not sum to the result count")

    return problems
