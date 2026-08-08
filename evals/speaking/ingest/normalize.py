"""Normalise a provider response into the canonical utterance model.

SPEAK-EVAL-005, section 8.1. Converts a Gladia V2 result into provider-neutral
records, and refuses the ones that are malformed.

Two rules govern this module.

**The raw response is never mutated.** Normalisation is lossy and this
normaliser will have bugs. The raw payload is stored first and hash-linked to
whatever comes out, so a defect found in three months can be repaired by
re-normalising rather than re-paying for transcription.

**Speaker 0 is not the candidate.** Gladia numbers speakers by first appearance
and has no idea who is who. In the project's own two-speaker fixture, speaker 0
is the *examiner* -- the examiner speaks first, as they do in every real IELTS
recording. A pipeline that hardcoded `speaker == 0 -> candidate` would therefore
score the examiner and be wrong on essentially every item while looking
plausible on none of them. So normalisation assigns role `unresolved` to every
utterance and a human assigns roles later (see roles.py).

The normaliser rejects rather than repairs. A negative duration, a word outside
its utterance, a non-monotonic word sequence -- each is a signal that an
assumption is wrong, and silently clipping the value to make schema validation
pass would destroy the evidence that anything was ever wrong.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "normalized-transcript/v1"
NORMALIZER_VERSION = "1.0.0"

# Roles. `unresolved` is the only value normalisation may produce.
ROLE_CANDIDATE = "candidate"
ROLE_EXAMINER = "examiner"
ROLE_OTHER = "other"
ROLE_UNRESOLVED = "unresolved"

VALID_ROLES = {ROLE_CANDIDATE, ROLE_EXAMINER, ROLE_OTHER, ROLE_UNRESOLVED}

# Floating point slack when comparing times. Provider timings are milliseconds
# rendered as floats; an exact comparison would reject valid data over the last
# bit of a double.
EPSILON = 1e-6


class NormalizationError(ValueError):
    """The response cannot be normalised without inventing something."""


@dataclass(frozen=True)
class Word:
    word: str
    start_s: float
    end_s: float
    confidence: float | None = None


@dataclass
class Utterance:
    utterance_id: str
    provider_speaker: int | None
    role: str
    start_s: float
    end_s: float
    text: str
    normalized_text: str
    language: str | None = None
    confidence: float | None = None
    channel: int | None = None
    words: list[Word] = field(default_factory=list)
    overlap: bool = False
    edit_reason: str | None = None
    edited_by: str | None = None

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class NormalizedTranscript:
    schema_version: str
    normalizer_version: str
    item_id: str
    provider: str
    api_version: str
    request_profile_hash: str
    external_docs_reviewed_at: str
    job_id: str
    idempotency_key: str
    raw_sha256: str
    """Hash-link back to the exact raw response this was derived from. Without
    it, a normalised transcript is an assertion about a provider response that
    can no longer be checked."""

    audio_duration_s: float | None
    utterances: list[Utterance]
    provider_speakers: list[int]
    quarantine: list[str] = field(default_factory=list)
    """Reasons this transcript may not be used. Non-empty means unusable; the
    record is still written, because a discarded failure teaches nobody why."""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["utterances"] = [asdict(u) for u in self.utterances]
        return payload

    def content_sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def usable(self) -> bool:
        return not self.quarantine


def normalize_text(text: str) -> str:
    """Collapse whitespace. Gladia emits leading spaces on continuation words."""
    return " ".join(text.split())


def _validate_word_sequence(words: list[Word], utterance_id: str, start_s: float, end_s: float) -> list[str]:
    """Return the problems with one utterance's words.

    Checked rather than trusted because word times are what SPEAK-EVAL-006 cuts
    clips on and what an explanation's evidence offsets point at. A word that
    claims to end before it starts becomes a negative-length clip, and the first
    place anyone notices is a corrupt audio file.
    """
    problems = []
    previous_end = None

    for index, word in enumerate(words):
        where = f"{utterance_id}.word[{index}]"

        if word.end_s < word.start_s - EPSILON:
            problems.append(
                f"{where}: negative duration ({word.start_s:.3f} -> {word.end_s:.3f})"
            )
        if word.start_s < start_s - EPSILON or word.end_s > end_s + EPSILON:
            problems.append(
                f"{where}: word [{word.start_s:.3f}, {word.end_s:.3f}] falls outside "
                f"its utterance [{start_s:.3f}, {end_s:.3f}]"
            )
        if previous_end is not None and word.start_s < previous_end - EPSILON:
            problems.append(
                f"{where}: starts at {word.start_s:.3f} before the previous word "
                f"ended at {previous_end:.3f}; word order is not monotonic"
            )
        previous_end = word.end_s

    return problems


def normalize_gladia(
    raw: dict[str, Any],
    *,
    item_id: str,
    job_id: str,
    idempotency_key: str,
    raw_sha256: str,
    provider: str = "gladia",
    api_version: str = "v2",
    request_profile_hash: str = "",
    external_docs_reviewed_at: str = "",
    audio_duration_s: float | None = None,
) -> NormalizedTranscript:
    """Convert a completed Gladia V2 result into the canonical model."""
    result = raw.get("result")
    if not isinstance(result, dict):
        raise NormalizationError("response has no `result` object")

    transcription = result.get("transcription")
    if not isinstance(transcription, dict):
        raise NormalizationError("response has no `result.transcription` object")

    raw_utterances = transcription.get("utterances")
    if not isinstance(raw_utterances, list):
        raise NormalizationError("response has no `utterances` list")

    metadata = result.get("metadata") or {}
    duration = audio_duration_s or metadata.get("audio_duration")

    utterances: list[Utterance] = []
    quarantine: list[str] = []
    speakers: set[int] = set()
    previous_end: float | None = None

    for index, entry in enumerate(raw_utterances):
        utterance_id = f"u{index:04d}"

        start = entry.get("start")
        end = entry.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            quarantine.append(f"{utterance_id}: missing or non-numeric start/end")
            continue
        if end < start - EPSILON:
            quarantine.append(
                f"{utterance_id}: negative duration ({start:.3f} -> {end:.3f})"
            )
            continue
        if duration is not None and end > duration + 1.0:
            # Beyond the file's own length by more than a second: the timings
            # belong to different audio than the metadata describes.
            quarantine.append(
                f"{utterance_id}: ends at {end:.3f}s, past the {duration:.3f}s audio"
            )
            continue

        speaker = entry.get("speaker")
        if isinstance(speaker, int):
            speakers.add(speaker)

        words = [
            Word(
                word=str(w.get("word", "")),
                start_s=float(w.get("start", 0.0)),
                end_s=float(w.get("end", 0.0)),
                confidence=w.get("confidence"),
            )
            for w in (entry.get("words") or [])
            if isinstance(w, dict)
        ]

        word_problems = _validate_word_sequence(words, utterance_id, float(start), float(end))
        if word_problems:
            quarantine.extend(word_problems)
            continue

        # Overlap with the previous utterance. Flagged, not resolved: whether an
        # overlap invalidates the item is a review decision, and the reviewer
        # needs to see it flagged to make it.
        overlap = previous_end is not None and start < previous_end - EPSILON
        previous_end = max(previous_end or 0.0, float(end))

        text = str(entry.get("text", ""))
        utterances.append(
            Utterance(
                utterance_id=utterance_id,
                provider_speaker=speaker if isinstance(speaker, int) else None,
                # Always unresolved. See the module docstring: in this project's
                # own fixture speaker 0 is the examiner, so any automatic
                # assignment would be wrong from the first item.
                role=ROLE_UNRESOLVED,
                start_s=float(start),
                end_s=float(end),
                text=text,
                normalized_text=normalize_text(text),
                language=entry.get("language"),
                confidence=entry.get("confidence"),
                channel=entry.get("channel"),
                words=words,
                overlap=overlap,
            )
        )

    if not utterances:
        quarantine.append("no usable utterances survived normalisation")

    return NormalizedTranscript(
        schema_version=SCHEMA_VERSION,
        normalizer_version=NORMALIZER_VERSION,
        item_id=item_id,
        provider=provider,
        api_version=api_version,
        request_profile_hash=request_profile_hash,
        external_docs_reviewed_at=external_docs_reviewed_at,
        job_id=job_id,
        idempotency_key=idempotency_key,
        raw_sha256=raw_sha256,
        audio_duration_s=float(duration) if duration is not None else None,
        utterances=utterances,
        provider_speakers=sorted(speakers),
        quarantine=quarantine,
    )


def speaker_summary(transcript: NormalizedTranscript) -> list[dict[str, Any]]:
    """Per-speaker totals and first turns, for the review page.

    A reviewer decides roles from evidence: who speaks first, who speaks longer,
    and what they actually say. This assembles that evidence; it does not draw
    the conclusion.
    """
    by_speaker: dict[int | None, list[Utterance]] = {}
    for utterance in transcript.utterances:
        by_speaker.setdefault(utterance.provider_speaker, []).append(utterance)

    summary = []
    for speaker, items in sorted(
        by_speaker.items(), key=lambda pair: (pair[0] is None, pair[0])
    ):
        total = sum(u.duration_s for u in items)
        summary.append({
            "provider_speaker": speaker,
            "utterance_count": len(items),
            "total_duration_s": round(total, 3),
            "share_of_speech": round(
                total / sum(u.duration_s for u in transcript.utterances), 4
            ) if transcript.utterances else 0.0,
            "first_turn_s": round(min(u.start_s for u in items), 3),
            "excerpts": [
                {
                    "utterance_id": u.utterance_id,
                    "start_s": round(u.start_s, 3),
                    "end_s": round(u.end_s, 3),
                    "text": u.normalized_text,
                }
                for u in items[:3]
            ],
        })
    return summary
