"""Speaker role annotation (SPEAK-EVAL-005, section 8.2).

A provider speaker id is a number. A role is a judgement. This module keeps them
apart, and refuses to turn the first into the second automatically.

The rule the ticket states as an acceptance criterion -- *`speaker 0` is never
automatically treated as candidate* -- is not a stylistic preference. Gladia
numbers speakers by first appearance, and in an IELTS recording the examiner
speaks first. So the convenient assumption is not merely unsafe, it is
*backwards*: this project's own fixture has speaker 0 as the examiner, and a
pipeline that assumed otherwise would score the interviewer on every item.

An annotation is a separate versioned file. The raw provider response and the
normalised transcript are never mutated, so a role mapping can be corrected, and
re-corrected, without re-ingesting anything.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.speaking.ingest.normalize import (
    ROLE_CANDIDATE,
    ROLE_EXAMINER,
    VALID_ROLES,
    NormalizedTranscript,
    Utterance,
)

SCHEMA_VERSION = "role-annotation/v1"

# The plan requires a second reviewer for anything that can gate a release. One
# reviewer is a hypothesis; two who agree independently is evidence.
REVIEWERS_REQUIRED_FOR_GATING = 2


class RoleAnnotationError(ValueError):
    """The annotation cannot be applied as given."""


@dataclass
class BoundaryEdit:
    """A manual correction to an utterance boundary, with its audit record.

    `reason` is required. An unexplained boundary edit is indistinguishable from
    a mistake, and the person who has to judge that is not the person who made it.
    """

    utterance_id: str
    field: str
    from_s: float
    to_s: float
    reason: str
    edited_by: str


@dataclass
class RoleAnnotation:
    schema_version: str
    item_id: str
    normalized_sha256: str
    """Hash-link to the transcript this annotation describes. If the transcript
    is re-normalised, this no longer applies and the mismatch is detectable
    rather than silent."""

    speaker_roles: dict[str, str]
    """provider speaker id (as a string, since JSON keys are strings) -> role."""

    reviewers: list[str] = field(default_factory=list)
    reviewed_at: str | None = None
    boundary_edits: list[BoundaryEdit] = field(default_factory=list)
    notes: str = ""
    contaminated: bool = False
    """Set by a reviewer when examiner speech, crosstalk or a third voice makes
    the candidate audio unusable. An excluded item with a reason is data; an
    item quietly scored through contamination is a wrong number."""
    exclusion_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["boundary_edits"] = [asdict(e) for e in self.boundary_edits]
        return payload

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")

    @classmethod
    def load(cls, path: Path) -> "RoleAnnotation":
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        edits = [BoundaryEdit(**e) for e in payload.pop("boundary_edits", [])]
        return cls(boundary_edits=edits, **payload)


def new_annotation(transcript: NormalizedTranscript) -> RoleAnnotation:
    """An empty annotation for a reviewer to fill in.

    Every speaker starts unassigned. There is deliberately no default and no
    "suggested" mapping: a suggestion is what gets accepted without looking,
    and the whole value of this step is that somebody looked.
    """
    return RoleAnnotation(
        schema_version=SCHEMA_VERSION,
        item_id=transcript.item_id,
        normalized_sha256=transcript.content_sha256(),
        speaker_roles={},
    )


def validate_annotation(
    annotation: RoleAnnotation,
    transcript: NormalizedTranscript,
    *,
    for_gating: bool = False,
) -> list[str]:
    """Check an annotation against its transcript. Empty list means usable."""
    problems: list[str] = []

    if annotation.normalized_sha256 != transcript.content_sha256():
        problems.append(
            "annotation was written against a different transcript "
            f"({annotation.normalized_sha256[:12]}... vs "
            f"{transcript.content_sha256()[:12]}...); re-review after re-normalising"
        )

    observed = {str(s) for s in transcript.provider_speakers}
    assigned = set(annotation.speaker_roles)

    for missing in sorted(observed - assigned):
        problems.append(
            f"provider speaker {missing} has no role assigned; roles must be "
            f"assigned, never defaulted"
        )
    for extra in sorted(assigned - observed):
        problems.append(f"role assigned to speaker {extra}, who does not appear in the transcript")

    for speaker, role in sorted(annotation.speaker_roles.items()):
        if role not in VALID_ROLES:
            problems.append(f"speaker {speaker}: {role!r} is not a valid role")

    candidates = [s for s, r in annotation.speaker_roles.items() if r == ROLE_CANDIDATE]
    if not candidates:
        problems.append("no speaker is marked as the candidate; there is nothing to score")
    elif len(candidates) > 1:
        problems.append(
            f"{len(candidates)} speakers are marked as the candidate "
            f"({', '.join(sorted(candidates))}); an IELTS item has exactly one"
        )

    # More or fewer than two speakers is not automatically an error -- an
    # introduction or an interpreter is legitimate -- but it must be seen.
    speaker_count = len(transcript.provider_speakers)
    if speaker_count != 2 and not annotation.notes:
        problems.append(
            f"the recording has {speaker_count} speakers rather than the expected 2, "
            f"and no reviewer note explains it"
        )

    if annotation.contaminated and not annotation.exclusion_reason:
        problems.append("item is marked contaminated with no exclusion reason recorded")

    for edit in annotation.boundary_edits:
        if not edit.reason:
            problems.append(f"boundary edit on {edit.utterance_id} has no reason")
        if not edit.edited_by:
            problems.append(f"boundary edit on {edit.utterance_id} names no editor")

    if for_gating:
        if len(annotation.reviewers) < REVIEWERS_REQUIRED_FOR_GATING:
            problems.append(
                f"a gating item needs {REVIEWERS_REQUIRED_FOR_GATING} reviewers; "
                f"this annotation names {len(annotation.reviewers)}"
            )
        if not annotation.reviewed_at:
            problems.append("a gating item must record when it was reviewed")

    return problems


def apply_roles(
    transcript: NormalizedTranscript,
    annotation: RoleAnnotation,
) -> NormalizedTranscript:
    """Return a copy of the transcript with roles and boundary edits applied.

    A copy, not an in-place update. The normalised transcript is an artifact of
    the provider response; the annotated transcript is an artifact of a review.
    Collapsing them loses the ability to say which is which.
    """
    problems = validate_annotation(annotation, transcript)
    if problems:
        raise RoleAnnotationError("; ".join(problems))

    edits_by_utterance: dict[str, list[BoundaryEdit]] = {}
    for edit in annotation.boundary_edits:
        edits_by_utterance.setdefault(edit.utterance_id, []).append(edit)

    updated: list[Utterance] = []
    for utterance in transcript.utterances:
        role = annotation.speaker_roles.get(str(utterance.provider_speaker))
        start, end = utterance.start_s, utterance.end_s
        reason, editor = utterance.edit_reason, utterance.edited_by

        for edit in edits_by_utterance.get(utterance.utterance_id, []):
            if edit.field == "start_s":
                start = edit.to_s
            elif edit.field == "end_s":
                end = edit.to_s
            else:
                raise RoleAnnotationError(
                    f"boundary edit on {edit.utterance_id} names unknown field {edit.field!r}"
                )
            reason = edit.reason
            editor = edit.edited_by

        if end < start:
            raise RoleAnnotationError(
                f"boundary edit on {utterance.utterance_id} produced a negative "
                f"duration ({start:.3f} -> {end:.3f})"
            )

        updated.append(
            Utterance(
                utterance_id=utterance.utterance_id,
                provider_speaker=utterance.provider_speaker,
                role=role or utterance.role,
                start_s=start,
                end_s=end,
                text=utterance.text,
                normalized_text=utterance.normalized_text,
                language=utterance.language,
                confidence=utterance.confidence,
                channel=utterance.channel,
                words=utterance.words,
                overlap=utterance.overlap,
                edit_reason=reason,
                edited_by=editor,
            )
        )

    return NormalizedTranscript(
        schema_version=transcript.schema_version,
        normalizer_version=transcript.normalizer_version,
        item_id=transcript.item_id,
        provider=transcript.provider,
        api_version=transcript.api_version,
        request_profile_hash=transcript.request_profile_hash,
        external_docs_reviewed_at=transcript.external_docs_reviewed_at,
        job_id=transcript.job_id,
        idempotency_key=transcript.idempotency_key,
        raw_sha256=transcript.raw_sha256,
        audio_duration_s=transcript.audio_duration_s,
        utterances=updated,
        provider_speakers=transcript.provider_speakers,
        quarantine=list(transcript.quarantine),
    )


def candidate_utterances(transcript: NormalizedTranscript) -> list[Utterance]:
    """The candidate's turns, in time order.

    Raises when no role has been assigned. Returning an empty list would let a
    caller compute metrics over nothing and report a confident zero.
    """
    if all(u.role != ROLE_CANDIDATE for u in transcript.utterances):
        raise RoleAnnotationError(
            "no utterance is assigned to the candidate; apply a reviewed role "
            "annotation before extracting candidate speech"
        )
    return sorted(
        (u for u in transcript.utterances if u.role == ROLE_CANDIDATE),
        key=lambda u: u.start_s,
    )


def examiner_utterances(transcript: NormalizedTranscript) -> list[Utterance]:
    return sorted(
        (u for u in transcript.utterances if u.role == ROLE_EXAMINER),
        key=lambda u: u.start_s,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
