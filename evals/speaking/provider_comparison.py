"""Compare transcription providers on identical audio (SPEAK-EVAL-011).

The ticket's acceptance is that "production rollout requires an approved
comparison report". This produces the report; approving it is a human decision.

Compared on the same clips, because the question is not "how good is Gladia" but
"does swapping the engine change the score a candidate receives". Those are
different questions and only the second one matters here.

What is measured, and why each one is not optional:

  WER              the standard measure, but the least decisive: a transcript
                   can be word-perfect and still produce a different band.
  filler retention "um", "uh", "you know". A provider that tidies them away
                   makes a hesitant candidate read as fluent -- the transcript
                   improves and the assessment gets worse. This is the metric
                   most likely to differ and least likely to be looked at.
  word timing      Fluency is computed from word timestamps. A provider with
                   good text and loose timings damages exactly the criterion
                   that depends on it.
  score impact     the only one that decides anything: run both transcripts
                   through the scorer and compare the bands.
  latency, cost    operational, and the reason the incumbent is free.

Nothing here mutates the dataset. A comparison that could rewrite a human label
would be able to make either provider look correct.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Deliberately explicit rather than a regex over "words ending in m". These are
# the tokens whose SURVIVAL matters: a provider that removes them is editing the
# evidence Fluency and Coherence is assessed on.
FILLERS = {
    "um", "uh", "erm", "er", "ah", "hmm", "mm",
    "like", "well", "so", "actually", "basically", "literally",
    "you know", "i mean", "sort of", "kind of",
}

SINGLE_WORD_FILLERS = {f for f in FILLERS if " " not in f}
MULTI_WORD_FILLERS = {f for f in FILLERS if " " in f}


def normalise(text: str) -> list[str]:
    """Lowercase, strip punctuation, split. Used for WER only."""
    cleaned = re.sub(r"[^\w\s']", " ", text.lower())
    return cleaned.split()


def word_error_rate(reference: str, hypothesis: str) -> float | None:
    """Levenshtein over words, normalised by reference length.

    Returns None for an empty reference rather than 0.0 or 1.0. A WER against
    nothing is undefined, and both constants would be read as a measurement.
    """
    ref = normalise(reference)
    hyp = normalise(hypothesis)
    if not ref:
        return None

    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            )
        previous = current

    return round(previous[-1] / len(ref), 4)


def count_fillers(text: str) -> dict[str, int]:
    lowered = " " + re.sub(r"[^\w\s']", " ", text.lower()) + " "
    counts: dict[str, int] = {}

    for phrase in MULTI_WORD_FILLERS:
        found = lowered.count(f" {phrase} ")
        if found:
            counts[phrase] = found

    for token in lowered.split():
        if token in SINGLE_WORD_FILLERS:
            counts[token] = counts.get(token, 0) + 1

    return counts


@dataclass
class TimingComparison:
    words_a: int
    words_b: int
    mean_abs_start_delta_s: float | None = None
    max_abs_start_delta_s: float | None = None
    duration_delta_s: float | None = None


@dataclass
class ItemComparison:
    item_id: str

    wer: float | None = None
    transcript_words_a: int = 0
    transcript_words_b: int = 0

    fillers_a: int = 0
    fillers_b: int = 0
    filler_retention: float | None = None

    timing: TimingComparison | None = None

    band_a: float | None = None
    band_b: float | None = None
    band_delta: float | None = None

    latency_ms_a: int | None = None
    latency_ms_b: int | None = None
    cost_a: float | None = None
    cost_b: float | None = None

    notes: list[str] = field(default_factory=list)


def compare_transcriptions(
    item_id: str,
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    band_a: float | None = None,
    band_b: float | None = None,
) -> ItemComparison:
    """Compare two /stt responses for one clip. `a` is the incumbent."""
    text_a = (a.get("transcript") or "").strip()
    text_b = (b.get("transcript") or "").strip()

    comparison = ItemComparison(
        item_id=item_id,
        wer=word_error_rate(text_a, text_b),
        transcript_words_a=len(normalise(text_a)),
        transcript_words_b=len(normalise(text_b)),
    )

    fillers_a = count_fillers(text_a)
    fillers_b = count_fillers(text_b)
    comparison.fillers_a = sum(fillers_a.values())
    comparison.fillers_b = sum(fillers_b.values())

    if comparison.fillers_a:
        # Above 1.0 means the challenger found MORE hesitation, which is not
        # automatically wrong -- it may simply be more faithful.
        comparison.filler_retention = round(
            comparison.fillers_b / comparison.fillers_a, 4
        )
        if comparison.filler_retention < 0.5:
            comparison.notes.append(
                f"Challenger retained {comparison.filler_retention:.0%} of the "
                f"incumbent's hesitation markers. A tidier transcript makes a "
                f"hesitant candidate read as fluent."
            )

    comparison.timing = _compare_timings(a, b)

    provenance_a = a.get("provenance") or {}
    provenance_b = b.get("provenance") or {}
    comparison.latency_ms_a = provenance_a.get("latency_ms")
    comparison.latency_ms_b = provenance_b.get("latency_ms")
    comparison.cost_a = provenance_a.get("estimated_cost_usd")
    comparison.cost_b = provenance_b.get("estimated_cost_usd")

    comparison.band_a = band_a
    comparison.band_b = band_b
    if band_a is not None and band_b is not None:
        comparison.band_delta = round(band_b - band_a, 2)
        if abs(comparison.band_delta) >= 0.5:
            comparison.notes.append(
                f"Swapping the provider moved the band by {comparison.band_delta:+.1f}. "
                f"This is the only measurement here that decides anything."
            )

    return comparison


def _compare_timings(a: dict[str, Any], b: dict[str, Any]) -> TimingComparison:
    words_a = a.get("words") or []
    words_b = b.get("words") or []

    timing = TimingComparison(words_a=len(words_a), words_b=len(words_b))

    duration_a = a.get("duration_s")
    duration_b = b.get("duration_s")
    if isinstance(duration_a, (int, float)) and isinstance(duration_b, (int, float)):
        timing.duration_delta_s = round(duration_b - duration_a, 3)

    # Compared positionally over the shared prefix. Crude, and honest about it:
    # a proper alignment would need the WER edit path, and the number is a
    # smoke signal for "the timings are wildly different", not a fine measure.
    paired = list(zip(words_a, words_b))
    if paired:
        deltas = [
            abs(float(x.get("start", 0.0)) - float(y.get("start", 0.0)))
            for x, y in paired
        ]
        timing.mean_abs_start_delta_s = round(sum(deltas) / len(deltas), 3)
        timing.max_abs_start_delta_s = round(max(deltas), 3)

    return timing


@dataclass
class ComparisonReport:
    incumbent: str
    challenger: str
    items: list[ItemComparison] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.items)

    def summary(self) -> dict[str, Any]:
        def mean(values: Iterable[float | None]) -> float | None:
            present = [v for v in values if isinstance(v, (int, float))]
            return round(sum(present) / len(present), 4) if present else None

        band_deltas = [i.band_delta for i in self.items if i.band_delta is not None]
        moved = [d for d in band_deltas if abs(d) >= 0.5]

        return {
            "incumbent": self.incumbent,
            "challenger": self.challenger,
            "n": self.n,
            "mean_wer": mean(i.wer for i in self.items),
            "mean_filler_retention": mean(i.filler_retention for i in self.items),
            "mean_abs_start_delta_s": mean(
                i.timing.mean_abs_start_delta_s for i in self.items if i.timing
            ),
            "mean_band_delta": mean(band_deltas),
            "items_where_band_moved_half_or_more": len(moved),
            "total_cost_incumbent": mean(i.cost_a for i in self.items),
            "total_cost_challenger": mean(i.cost_b for i in self.items),
            "mean_latency_ms_incumbent": mean(i.latency_ms_a for i in self.items),
            "mean_latency_ms_challenger": mean(i.latency_ms_b for i in self.items),
            # Never inferred. The recommendation is a human decision and the
            # report deliberately does not contain one -- a field called
            # "recommendation" gets read as the answer.
            "verdict": "for human review",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "items": [asdict(item) for item in self.items],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
