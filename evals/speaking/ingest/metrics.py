"""Segmentation and preparation metrics (SPEAK-EVAL-006, section 8.4).

These measure the *source preparation*, not the scoring. They answer one
question: is the audio we are about to score actually the candidate?

That question has to be answered before any band is believed, because every
failure mode here is silent. If the diarizer swapped the speakers, the pipeline
scores the examiner and returns a plausible band. If two seconds of examiner
speech leak into a clip, fluency shifts and nothing reports why. A band computed
on badly prepared audio is not a noisy measurement of the candidate; it is a
precise measurement of something else.

Metrics computed here, all time-weighted:

  candidate_precision   included candidate time / all included time
                        -- "of what we are scoring, how much is really them"
  candidate_recall      included candidate time / all true candidate time
                        -- "of what they said, how much did we keep"
  contamination_s / _pct   examiner speech inside candidate clips
  word_attribution_accuracy   per-word speaker correctness, time-weighted
  boundary_mae          mean absolute error of answer boundaries
  unresolved_s          time attributed to no confident speaker

The hard validity rule is applied last: an item with an unresolved role,
material contamination, or missing candidate speech is EXCLUDED with a reason,
not scored with a caveat. Thresholds are configurable because the plan is
explicit that they should be chosen after a pilot reveals what is achievable,
not guessed in advance and then quietly lived with.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from evals.speaking.ingest.clips import ClipManifest
from evals.speaking.ingest.normalize import (
    ROLE_CANDIDATE,
    ROLE_UNRESOLVED,
    NormalizedTranscript,
)

Interval = tuple[float, float]


@dataclass
class ValidityThresholds:
    """Where an item stops being usable.

    Defaults are deliberately strict, and deliberately provisional. Section 8.4
    says to set them after an annotated pilot; until that pilot exists these are
    starting values, and the field names say what they mean so a future change
    is a decision rather than a tweak.
    """

    max_contamination_pct: float = 5.0
    min_candidate_recall: float = 0.90
    min_candidate_precision: float = 0.95
    max_unresolved_pct: float = 2.0
    min_candidate_duration_s: float = 20.0


@dataclass
class SegmentationMetrics:
    item_id: str

    total_source_s: float
    true_candidate_s: float
    included_s: float

    candidate_precision: float
    candidate_recall: float
    contamination_s: float
    contamination_pct: float
    unresolved_s: float
    unresolved_pct: float

    word_attribution_accuracy: float | None = None
    boundary_mae_s: float | None = None
    boundary_errors_s: list[float] = field(default_factory=list)

    overlap_regions: int = 0
    overlap_s: float = 0.0

    valid: bool = True
    exclusion_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -- interval arithmetic -----------------------------------------------------


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Merge overlapping intervals.

    Every metric here is a ratio of durations, and double-counting an
    overlapping region inflates the numerator. Merging first is what keeps
    precision from exceeding 1.0 on a recording with crosstalk.
    """
    ordered = sorted((s, e) for s, e in intervals if e > s)
    if not ordered:
        return []

    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def total(intervals: Iterable[Interval]) -> float:
    return sum(end - start for start, end in merge(intervals))


def intersect(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for a_start, a_end in merge(a):
        for b_start, b_end in merge(b):
            start, end = max(a_start, b_start), min(a_end, b_end)
            if end > start:
                out.append((start, end))
    return out


# -- metrics -----------------------------------------------------------------


def compute_metrics(
    manifest: ClipManifest,
    transcript: NormalizedTranscript,
    ground_truth: dict[str, Any] | None = None,
    *,
    thresholds: ValidityThresholds | None = None,
) -> SegmentationMetrics:
    """Measure how well the prepared clips isolate the candidate.

    `ground_truth`, when supplied, is a manually annotated (or, for a generated
    fixture, exactly known) turn list. Without it recall and word attribution
    cannot be computed and are reported as None rather than as a number derived
    from the pipeline's own output -- which would be the pipeline grading itself.
    """
    thresholds = thresholds or ValidityThresholds()

    included = merge([(c.source_start_s, c.source_end_s) for c in manifest.clips])
    included_s = total(included)

    if ground_truth:
        truth_turns = ground_truth.get("turns", [])
        true_candidate = merge(
            [(t["start_s"], t["end_s"]) for t in truth_turns if t["role"] == ROLE_CANDIDATE]
        )
        true_examiner = merge(
            [(t["start_s"], t["end_s"]) for t in truth_turns if t["role"] == "examiner"]
        )
        total_source_s = float(ground_truth.get("total_duration_s") or 0.0)
    else:
        # Fall back to the annotated transcript. Honest but weaker: it measures
        # the clipper against the diarizer, and cannot see an error they share.
        true_candidate = merge(
            [(u.start_s, u.end_s) for u in transcript.utterances if u.role == ROLE_CANDIDATE]
        )
        true_examiner = merge(
            [(u.start_s, u.end_s) for u in transcript.utterances if u.role != ROLE_CANDIDATE]
        )
        total_source_s = float(transcript.audio_duration_s or 0.0)

    true_candidate_s = total(true_candidate)

    kept_candidate_s = total(intersect(included, true_candidate))
    contamination_s = total(intersect(included, true_examiner))

    unresolved = merge(
        [(u.start_s, u.end_s) for u in transcript.utterances if u.role == ROLE_UNRESOLVED]
    )
    unresolved_s = total(unresolved)

    overlaps = [u for u in transcript.utterances if u.overlap]

    metrics = SegmentationMetrics(
        item_id=manifest.item_id,
        total_source_s=round(total_source_s, 4),
        true_candidate_s=round(true_candidate_s, 4),
        included_s=round(included_s, 4),
        candidate_precision=round(kept_candidate_s / included_s, 4) if included_s else 0.0,
        candidate_recall=round(kept_candidate_s / true_candidate_s, 4) if true_candidate_s else 0.0,
        contamination_s=round(contamination_s, 4),
        contamination_pct=round(100.0 * contamination_s / included_s, 4) if included_s else 0.0,
        unresolved_s=round(unresolved_s, 4),
        unresolved_pct=round(100.0 * unresolved_s / total_source_s, 4) if total_source_s else 0.0,
        overlap_regions=len(overlaps),
        overlap_s=round(sum(u.duration_s for u in overlaps), 4),
    )

    if ground_truth:
        metrics.word_attribution_accuracy = _word_attribution(transcript, ground_truth)
        metrics.boundary_errors_s, metrics.boundary_mae_s = _boundary_error(
            manifest, ground_truth
        )

    _apply_validity_rule(metrics, transcript, thresholds)
    return metrics


def _word_attribution(
    transcript: NormalizedTranscript, ground_truth: dict[str, Any]
) -> float | None:
    """Time-weighted share of words assigned to the right speaker.

    Weighted by duration rather than counted: attributing "um" to the wrong
    speaker matters less than attributing a fifteen-second answer, and an
    unweighted count says they are the same.
    """
    truth = [(t["start_s"], t["end_s"], t["role"]) for t in ground_truth.get("turns", [])]
    if not truth:
        return None

    correct = 0.0
    measured = 0.0

    for utterance in transcript.utterances:
        for word in utterance.words:
            duration = word.end_s - word.start_s
            if duration <= 0:
                continue
            midpoint = (word.start_s + word.end_s) / 2.0
            actual_role = next(
                (role for start, end, role in truth if start <= midpoint <= end), None
            )
            if actual_role is None:
                continue
            measured += duration
            if actual_role == utterance.role:
                correct += duration

    return round(correct / measured, 4) if measured else None


def _boundary_error(
    manifest: ClipManifest, ground_truth: dict[str, Any]
) -> tuple[list[float], float | None]:
    """Absolute error between each clip boundary and the true answer boundary."""
    truth_answers = [
        (t["start_s"], t["end_s"])
        for t in ground_truth.get("turns", [])
        if t["role"] == ROLE_CANDIDATE
    ]
    if not truth_answers or not manifest.clips:
        return [], None

    errors: list[float] = []
    for clip in manifest.clips:
        nearest = min(
            truth_answers,
            key=lambda pair: abs(pair[0] - clip.source_start_s),
        )
        errors.append(round(abs(nearest[0] - clip.source_start_s), 4))
        errors.append(round(abs(nearest[1] - clip.source_end_s), 4))

    return errors, round(sum(errors) / len(errors), 4)


def _apply_validity_rule(
    metrics: SegmentationMetrics,
    transcript: NormalizedTranscript,
    thresholds: ValidityThresholds,
) -> None:
    """The hard rule: exclude with a reason rather than score with a caveat.

    Each reason names the measurement and the threshold, so the exclusion can be
    argued with. "Excluded: data quality" is not something anyone can act on.
    """
    reasons = metrics.exclusion_reasons

    unresolved_roles = [u for u in transcript.utterances if u.role == ROLE_UNRESOLVED]
    if unresolved_roles:
        reasons.append(
            f"{len(unresolved_roles)} utterance(s) have an unresolved speaker role; "
            f"a role must be reviewed, never assumed"
        )

    if metrics.contamination_pct > thresholds.max_contamination_pct:
        reasons.append(
            f"examiner contamination is {metrics.contamination_pct:.2f}% of included "
            f"audio, above the {thresholds.max_contamination_pct}% limit"
        )

    if metrics.candidate_recall < thresholds.min_candidate_recall:
        reasons.append(
            f"candidate recall is {metrics.candidate_recall:.3f}, below "
            f"{thresholds.min_candidate_recall}; too much of the answer was dropped"
        )

    if metrics.candidate_precision < thresholds.min_candidate_precision:
        reasons.append(
            f"candidate precision is {metrics.candidate_precision:.3f}, below "
            f"{thresholds.min_candidate_precision}; the clips contain too much "
            f"that is not the candidate"
        )

    if metrics.unresolved_pct > thresholds.max_unresolved_pct:
        reasons.append(
            f"{metrics.unresolved_pct:.2f}% of the recording is unresolved, above "
            f"the {thresholds.max_unresolved_pct}% limit"
        )

    if metrics.included_s < thresholds.min_candidate_duration_s:
        reasons.append(
            f"only {metrics.included_s:.1f}s of candidate speech was kept, below the "
            f"{thresholds.min_candidate_duration_s}s minimum; there is not enough "
            f"evidence to band four criteria"
        )

    metrics.valid = not reasons
