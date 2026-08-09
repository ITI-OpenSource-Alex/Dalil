"""Candidate-only audio construction (SPEAK-EVAL-006, section 8.3).

The scorer needs the student's speech, not the examiner's. Getting there is less
obvious than it sounds, and the obvious approach is wrong in a way that is very
hard to see afterwards.

**The trap.** Concatenate every candidate utterance into one file and score it.
The result contains joins where examiner turns used to be. Those joins are
silence. The prosody extractor cannot tell them from the candidate pausing, so
it counts them as hesitation, and a fluent candidate is marked down for the
examiner's questions. The metric that reports this is `words per minute`, and it
will look perfectly reasonable while being wrong.

**What this module does instead.** One clip per candidate *answer*. Within an
answer, every millisecond is preserved -- hesitation, repetition, self-correction
and all, because those are the phenomena Fluency and Coherence is defined over.
Between answers, nothing is joined: the clips stay separate and a manifest
records how they relate. A pause that never existed cannot be measured.

**Determinism.** Identical source plus identical annotation must produce
identical clip bytes. The ffmpeg command, its version, the ordered segment list
and the output hash all go in the manifest, so a hash mismatch on a re-run is a
signal rather than a mystery.

**Traceability.** Every clip carries the mapping between its own timeline and
the source timeline. An explanation that quotes the candidate at 4.2s into clip
3 can be resolved back to 31.9s in the original recording, which is what makes
the evidence checkable by a human with the source file.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evals.speaking.ingest.normalize import NormalizedTranscript, Utterance
from evals.speaking.ingest.roles import (
    ROLE_CANDIDATE,
    RoleAnnotationError,
    candidate_utterances,
    examiner_utterances,
)

SCHEMA_VERSION = "clip-manifest/v1"
BUILDER_VERSION = "1.0.0"

# Canonical output format, per section 8.3. One representation everywhere makes
# hashing and replay deterministic.
SAMPLE_RATE = 16000
CHANNELS = 1
CODEC = "pcm_s16le"

# Padding around an answer, to avoid clipping the first and last phoneme. Small
# and documented: too much pulls in examiner speech, none at all shaves the
# consonant off "students" and the transcript quietly changes.
BOUNDARY_PAD_S = 0.15

# A gap longer than this between two candidate utterances means the examiner
# spoke, or the candidate stopped and was prompted. Either way it is an answer
# boundary, not a pause inside one answer.
ANSWER_SPLIT_GAP_S = 1.5


class ClipError(RuntimeError):
    """Clip construction failed and no artifact should be trusted."""


@dataclass
class ClipSegment:
    """One candidate utterance inside a clip, in both timelines."""

    utterance_id: str
    source_start_s: float
    source_end_s: float
    clip_start_s: float
    clip_end_s: float
    text: str


@dataclass
class Clip:
    clip_id: str
    answer_index: int
    source_start_s: float
    source_end_s: float
    duration_s: float
    path: str | None
    sha256: str | None
    segments: list[ClipSegment] = field(default_factory=list)
    within_answer_pause_s: float = 0.0
    """Silence genuinely inside the answer. Preserved in the audio and reported
    here so a fluency reading can be sanity-checked against it."""

    def to_source_time(self, clip_time_s: float) -> float:
        """Map a time in this clip back to the source recording.

        The inverse of the cut. This is what lets an explanation's evidence
        offset be checked against the original audio by a human -- without it,
        "you hesitated at 4.2 seconds" refers to a file only the pipeline has.
        """
        for segment in self.segments:
            if segment.clip_start_s - 1e-6 <= clip_time_s <= segment.clip_end_s + 1e-6:
                offset = clip_time_s - segment.clip_start_s
                return segment.source_start_s + offset
        raise ClipError(
            f"clip time {clip_time_s:.3f}s falls outside every segment of {self.clip_id}"
        )


@dataclass
class ClipManifest:
    schema_version: str
    builder_version: str
    item_id: str
    normalized_sha256: str
    source_media_sha256: str
    source_duration_s: float | None
    sample_rate: int
    channels: int
    codec: str
    boundary_pad_s: float
    answer_split_gap_s: float
    ffmpeg_version: str
    clips: list[Clip] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    @property
    def total_candidate_duration_s(self) -> float:
        return sum(c.duration_s for c in self.clips)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clips"] = [asdict(c) for c in self.clips]
        return payload

    def content_sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")

    def locate(self, clip_id: str, clip_time_s: float) -> dict[str, float | str]:
        """Resolve a (clip, time) pair to a source time.

        The end of the traceability chain the ticket asks for: a band cites
        evidence, the evidence names a clip and an offset, and this turns that
        into a timestamp in the original recording.
        """
        for clip in self.clips:
            if clip.clip_id == clip_id:
                return {
                    "clip_id": clip_id,
                    "clip_time_s": round(clip_time_s, 4),
                    "source_time_s": round(clip.to_source_time(clip_time_s), 4),
                    "item_id": self.item_id,
                }
        raise ClipError(f"no clip {clip_id!r} in this manifest")


def ffmpeg_version() -> str:
    if shutil.which("ffmpeg") is None:
        raise ClipError("ffmpeg is not on PATH")
    out = subprocess.run(
        ["ffmpeg", "-version"], check=True, capture_output=True, text=True
    ).stdout
    return out.splitlines()[0].strip() if out else "unknown"


def group_into_answers(
    utterances: list[Utterance],
    *,
    split_gap_s: float = ANSWER_SPLIT_GAP_S,
) -> list[list[Utterance]]:
    """Group consecutive candidate utterances into answers.

    A provider emits an utterance per sentence-ish unit, so one answer arrives as
    several. Grouping them by gap keeps an answer whole -- which matters because
    the pauses *inside* an answer are exactly what must survive, and the gaps
    *between* answers are exactly what must not.
    """
    if not utterances:
        return []

    answers: list[list[Utterance]] = [[utterances[0]]]
    for previous, current in zip(utterances, utterances[1:]):
        if current.start_s - previous.end_s > split_gap_s:
            answers.append([current])
        else:
            answers[-1].append(current)
    return answers


def build_clips(
    transcript: NormalizedTranscript,
    source_media: Path,
    out_dir: Path,
    *,
    boundary_pad_s: float = BOUNDARY_PAD_S,
    split_gap_s: float = ANSWER_SPLIT_GAP_S,
    write_audio: bool = True,
) -> ClipManifest:
    """Cut one clip per candidate answer and record how to get back."""
    if not source_media.exists():
        raise ClipError(f"source media not found: {source_media}")

    try:
        candidate = candidate_utterances(transcript)
    except RoleAnnotationError as exc:
        raise ClipError(str(exc)) from exc

    examiner = examiner_utterances(transcript)
    answers = group_into_answers(candidate, split_gap_s=split_gap_s)

    manifest = ClipManifest(
        schema_version=SCHEMA_VERSION,
        builder_version=BUILDER_VERSION,
        item_id=transcript.item_id,
        normalized_sha256=transcript.content_sha256(),
        source_media_sha256=_file_sha256(source_media),
        source_duration_s=transcript.audio_duration_s,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        codec=CODEC,
        boundary_pad_s=boundary_pad_s,
        answer_split_gap_s=split_gap_s,
        ffmpeg_version=ffmpeg_version() if write_audio else "not-invoked",
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    for answer_index, group in enumerate(answers):
        raw_start = group[0].start_s
        raw_end = group[-1].end_s

        start = max(0.0, raw_start - boundary_pad_s)
        end = raw_end + boundary_pad_s
        if transcript.audio_duration_s is not None:
            end = min(end, transcript.audio_duration_s)

        # The pad must not swallow the examiner. If it would, pull it back to
        # the midpoint of the gap -- the alternative is examiner speech inside
        # the candidate clip, which is contamination the metrics will then
        # report as the candidate's.
        start = _pad_without_contamination(start, raw_start, examiner, before=True)
        end = _pad_without_contamination(end, raw_end, examiner, before=False)

        clip_id = f"{transcript.item_id}.a{answer_index:02d}"
        segments = []
        for utterance in group:
            segments.append(
                ClipSegment(
                    utterance_id=utterance.utterance_id,
                    source_start_s=round(utterance.start_s, 4),
                    source_end_s=round(utterance.end_s, 4),
                    # The clip is a single continuous cut, so clip time is just
                    # source time minus the clip's start. No arithmetic games,
                    # which is the point: a contiguous cut is trivially
                    # invertible and a concatenation is not.
                    clip_start_s=round(utterance.start_s - start, 4),
                    clip_end_s=round(utterance.end_s - start, 4),
                    text=utterance.normalized_text,
                )
            )

        within_pause = sum(
            later.start_s - earlier.end_s
            for earlier, later in zip(group, group[1:])
            if later.start_s > earlier.end_s
        )

        clip_path = out_dir / f"{clip_id}.wav"
        sha = None
        if write_audio:
            _cut(source_media, clip_path, start, end)
            sha = _file_sha256(clip_path)

        manifest.clips.append(
            Clip(
                clip_id=clip_id,
                answer_index=answer_index,
                source_start_s=round(start, 4),
                source_end_s=round(end, 4),
                duration_s=round(end - start, 4),
                path=str(clip_path) if write_audio else None,
                sha256=sha,
                segments=segments,
                within_answer_pause_s=round(within_pause, 4),
            )
        )

    if not manifest.clips:
        manifest.excluded.append("no candidate answers were found")

    return manifest


def _pad_without_contamination(
    padded: float,
    unpadded: float,
    examiner: list[Utterance],
    *,
    before: bool,
) -> float:
    """Clamp a boundary pad so it cannot reach into examiner speech."""
    for turn in examiner:
        if before and turn.end_s <= unpadded and padded < turn.end_s:
            return (turn.end_s + unpadded) / 2.0
        if not before and turn.start_s >= unpadded and padded > turn.start_s:
            return (turn.start_s + unpadded) / 2.0
    return padded


def _cut(source: Path, dest: Path, start_s: float, end_s: float) -> None:
    """Cut one contiguous span to canonical mono 16 kHz PCM.

    `-ss` before `-i` and re-encoding rather than stream-copying, both for
    determinism: a stream copy can only cut on a packet boundary, so the same
    request would land on a slightly different sample depending on the input
    encoding, and the output hash would wobble for no visible reason.
    """
    command = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.6f}",
        "-to", f"{end_s:.6f}",
        "-i", str(source),
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-c:a", CODEC,
        # Strip metadata: ffmpeg otherwise writes an encoder string, and the
        # output hash would then change with the ffmpeg build rather than with
        # the audio.
        "-map_metadata", "-1",
        "-fflags", "+bitexact",
        "-flags:a", "+bitexact",
        str(dest),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ClipError(
            f"ffmpeg failed cutting {start_s:.3f}-{end_s:.3f}: {result.stderr[-400:]}"
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
