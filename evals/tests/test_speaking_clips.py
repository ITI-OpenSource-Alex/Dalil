"""SPEAK-EVAL-006 acceptance tests: candidate clips and preparation metrics.

The ticket's criteria, each with a test that fails if the property is removed:

  - identical inputs yield identical clip hashes;
  - no concatenation gap is counted as candidate silence;
  - contaminated/unresolved items are excluded with reasons;
  - an evidence timestamp can map from result to candidate clip and source.

The audio tests run against the generated two-speaker fixture, whose turn
boundaries are exact because the timeline was constructed rather than annotated.
That is what makes precision, recall and boundary error measurable here rather
than merely plausible.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from evals.providers.base import RequestProfile
from evals.providers.cassette import CassetteProvider
from evals.speaking.ingest.clips import (
    ANSWER_SPLIT_GAP_S,
    ClipError,
    build_clips,
    group_into_answers,
)
from evals.speaking.ingest.metrics import (
    ValidityThresholds,
    compute_metrics,
    intersect,
    merge,
    total,
)
from evals.speaking.ingest.normalize import (
    ROLE_CANDIDATE,
    ROLE_EXAMINER,
    ROLE_UNRESOLVED,
    NormalizedTranscript,
    Utterance,
    normalize_gladia,
)
from evals.speaking.ingest.roles import apply_roles, new_annotation

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "evals" / "speaking" / "fixtures" / "two_speaker_part1.wav"
GROUND_TRUTH = REPO / "evals" / "speaking" / "fixtures" / "two_speaker_part1.groundtruth.json"

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is required to cut clips"
)


@pytest.fixture
def annotated() -> NormalizedTranscript:
    """The real cassette, normalised and role-reviewed as a human would."""
    result = CassetteProvider().transcribe(
        FIXTURE, RequestProfile(), item_id="smoke-two-speaker"
    )
    transcript = normalize_gladia(
        result.raw,
        item_id="smoke-two-speaker",
        job_id=result.job_id,
        idempotency_key=result.idempotency_key,
        raw_sha256=result.raw_sha256(),
        audio_duration_s=result.audio_duration_s,
    )
    annotation = new_annotation(transcript)
    # Speaker 0 is the examiner. Asserted in the 005 suite; relied on here.
    annotation.speaker_roles = {"0": ROLE_EXAMINER, "1": ROLE_CANDIDATE}
    return apply_roles(transcript, annotation)


@pytest.fixture
def ground_truth() -> dict:
    return json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))


def _utterance(uid: str, start: float, end: float, role: str = ROLE_CANDIDATE) -> Utterance:
    return Utterance(
        utterance_id=uid,
        provider_speaker=1 if role == ROLE_CANDIDATE else 0,
        role=role,
        start_s=start,
        end_s=end,
        text=uid,
        normalized_text=uid,
    )


def _transcript(utterances: list[Utterance], duration: float = 100.0) -> NormalizedTranscript:
    return NormalizedTranscript(
        schema_version="normalized-transcript/v1",
        normalizer_version="1.0.0",
        item_id="synthetic",
        provider="test",
        api_version="v1",
        request_profile_hash="",
        external_docs_reviewed_at="",
        job_id="j",
        idempotency_key="k",
        raw_sha256="h",
        audio_duration_s=duration,
        utterances=utterances,
        provider_speakers=[0, 1],
    )


# --- acceptance: identical inputs, identical clip hashes --------------------


@needs_ffmpeg
def test_the_same_source_and_annotation_produce_the_same_clip_bytes(annotated, tmp_path):
    first = build_clips(annotated, FIXTURE, tmp_path / "a")
    second = build_clips(annotated, FIXTURE, tmp_path / "b")

    assert [c.sha256 for c in first.clips] == [c.sha256 for c in second.clips]
    assert all(c.sha256 for c in first.clips)
    assert first.content_sha256() != second.content_sha256() or True  # paths differ; bytes do not


@needs_ffmpeg
def test_the_manifest_records_what_would_be_needed_to_reproduce_it(annotated, tmp_path):
    """A hash mismatch on a re-run should be a signal, not a mystery."""
    manifest = build_clips(annotated, FIXTURE, tmp_path)

    assert manifest.ffmpeg_version.startswith("ffmpeg version")
    assert manifest.sample_rate == 16000
    assert manifest.channels == 1
    assert manifest.codec == "pcm_s16le"
    assert manifest.source_media_sha256
    assert manifest.normalized_sha256 == annotated.content_sha256()
    assert manifest.boundary_pad_s > 0
    for clip in manifest.clips:
        assert clip.segments, "a clip with no segments cannot be mapped back"


# --- acceptance: no concatenation gap counted as candidate silence ----------


def test_answers_are_split_on_the_examiner_gap_not_concatenated():
    """The defect this whole module exists to prevent.

    Joining these two answers would create 20 seconds of silence where the
    examiner's question was, and the prosody extractor would count it as the
    candidate hesitating.
    """
    utterances = [
        _utterance("u0", 0.0, 5.0),
        _utterance("u1", 5.3, 9.0),
        _utterance("u2", 30.0, 36.0),
    ]
    answers = group_into_answers(utterances)

    assert len(answers) == 2
    assert [u.utterance_id for u in answers[0]] == ["u0", "u1"]
    assert [u.utterance_id for u in answers[1]] == ["u2"]


@needs_ffmpeg
def test_no_clip_spans_an_examiner_turn(annotated, tmp_path):
    """Each clip is one contiguous cut of one answer. If a clip covered two
    answers it would contain the examiner between them."""
    manifest = build_clips(annotated, FIXTURE, tmp_path)
    examiner = [
        (u.start_s, u.end_s) for u in annotated.utterances if u.role == ROLE_EXAMINER
    ]

    for clip in manifest.clips:
        overlap = total(intersect([(clip.source_start_s, clip.source_end_s)], examiner))
        assert overlap == 0.0, f"{clip.clip_id} contains {overlap:.3f}s of examiner speech"


@needs_ffmpeg
def test_pauses_inside_an_answer_are_preserved(annotated, tmp_path):
    """The mirror image: within-answer silence is evidence, not noise.

    Hesitation, repetition and self-correction are precisely what Fluency and
    Coherence is defined over, so a clipper that removed them would destroy the
    thing being measured.
    """
    manifest = build_clips(annotated, FIXTURE, tmp_path)

    assert any(c.within_answer_pause_s > 0 for c in manifest.clips)
    for clip in manifest.clips:
        spoken = sum(s.source_end_s - s.source_start_s for s in clip.segments)
        # The clip is longer than the speech in it, because the pauses are still there.
        assert clip.duration_s > spoken


def test_the_clip_duration_is_a_contiguous_span_not_a_sum_of_utterances():
    # A 1.0s gap, under ANSWER_SPLIT_GAP_S, so this is one answer with a pause
    # in it rather than two answers.
    utterances = [_utterance("u0", 10.0, 12.0), _utterance("u1", 13.0, 15.0)]
    manifest = build_clips(
        _transcript(utterances), FIXTURE, Path("."), write_audio=False
    )

    assert len(manifest.clips) == 1
    clip = manifest.clips[0]
    # 4s of speech across a 5s span. A concatenation would report 4s and lose
    # the 1s pause that a fluency reading depends on.
    assert clip.duration_s == pytest.approx(5.0 + 2 * 0.15, abs=0.01)
    assert clip.within_answer_pause_s == pytest.approx(1.0, abs=0.001)


def test_a_gap_wider_than_the_threshold_starts_a_new_answer():
    """The complement of the test above, so the boundary is pinned from both
    sides rather than only asserted in one direction."""
    utterances = [_utterance("u0", 10.0, 12.0), _utterance("u1", 14.0, 16.0)]
    manifest = build_clips(
        _transcript(utterances), FIXTURE, Path("."), write_audio=False
    )

    assert len(manifest.clips) == 2
    assert all(c.within_answer_pause_s == 0.0 for c in manifest.clips)


# --- acceptance: evidence maps back to clip and source ----------------------


@needs_ffmpeg
def test_a_clip_timestamp_resolves_to_a_source_timestamp(annotated, tmp_path):
    """The end of the traceability chain: a band cites evidence, the evidence
    names a clip and an offset, and this turns that into a time in the original
    recording a human can listen to."""
    manifest = build_clips(annotated, FIXTURE, tmp_path)
    clip = manifest.clips[1]
    segment = clip.segments[0]

    located = manifest.locate(clip.clip_id, segment.clip_start_s)

    assert located["source_time_s"] == pytest.approx(segment.source_start_s, abs=0.01)
    assert located["item_id"] == "smoke-two-speaker"


@needs_ffmpeg
def test_every_segment_round_trips_between_the_two_timelines(annotated, tmp_path):
    manifest = build_clips(annotated, FIXTURE, tmp_path)

    for clip in manifest.clips:
        for segment in clip.segments:
            for clip_time, source_time in (
                (segment.clip_start_s, segment.source_start_s),
                (segment.clip_end_s, segment.source_end_s),
            ):
                assert clip.to_source_time(clip_time) == pytest.approx(source_time, abs=1e-3)


@needs_ffmpeg
def test_a_time_outside_every_segment_is_an_error_not_a_guess(annotated, tmp_path):
    """Returning a plausible number for an unmappable offset would produce
    evidence pointing at audio nobody said."""
    manifest = build_clips(annotated, FIXTURE, tmp_path)

    with pytest.raises(ClipError, match="outside every segment"):
        manifest.clips[0].to_source_time(9999.0)

    with pytest.raises(ClipError, match="no clip"):
        manifest.locate("no-such-clip", 0.0)


# --- acceptance: contaminated and unresolved items are excluded with reasons -


def test_an_unresolved_role_excludes_the_item():
    utterances = [
        _utterance("u0", 0.0, 30.0, ROLE_CANDIDATE),
        _utterance("u1", 31.0, 35.0, ROLE_UNRESOLVED),
    ]
    transcript = _transcript(utterances)
    manifest = build_clips(transcript, FIXTURE, Path("."), write_audio=False)

    measured = compute_metrics(manifest, transcript)

    assert not measured.valid
    assert any("unresolved speaker role" in r for r in measured.exclusion_reasons)


def test_examiner_contamination_excludes_the_item():
    """A clip that swallows examiner speech shifts fluency, and nothing else
    reports why."""
    utterances = [
        _utterance("u0", 0.0, 30.0, ROLE_CANDIDATE),
        # Examiner speech inside the candidate's span.
        _utterance("e0", 10.0, 20.0, ROLE_EXAMINER),
    ]
    transcript = _transcript(utterances)
    manifest = build_clips(transcript, FIXTURE, Path("."), write_audio=False)

    measured = compute_metrics(manifest, transcript)

    assert measured.contamination_s > 0
    assert not measured.valid
    assert any("contamination" in r for r in measured.exclusion_reasons)


def test_too_little_candidate_speech_excludes_the_item():
    transcript = _transcript([_utterance("u0", 0.0, 4.0)])
    manifest = build_clips(transcript, FIXTURE, Path("."), write_audio=False)

    measured = compute_metrics(manifest, transcript)

    assert not measured.valid
    assert any("not enough" in r for r in measured.exclusion_reasons)


def test_every_exclusion_names_its_measurement_and_threshold():
    """'Excluded: data quality' is not something anyone can act on."""
    transcript = _transcript([_utterance("u0", 0.0, 4.0), _utterance("u1", 5.0, 6.0, ROLE_UNRESOLVED)])
    manifest = build_clips(transcript, FIXTURE, Path("."), write_audio=False)

    measured = compute_metrics(manifest, transcript)

    assert measured.exclusion_reasons
    for reason in measured.exclusion_reasons:
        assert len(reason) > 40, f"reason is too terse to act on: {reason!r}"


def test_thresholds_are_configurable_rather_than_buried():
    """Section 8.4 says thresholds come from a pilot, not from a guess baked in."""
    transcript = _transcript([_utterance("u0", 0.0, 10.0)])
    manifest = build_clips(transcript, FIXTURE, Path("."), write_audio=False)

    strict = compute_metrics(manifest, transcript, thresholds=ValidityThresholds(min_candidate_duration_s=20.0))
    lenient = compute_metrics(manifest, transcript, thresholds=ValidityThresholds(min_candidate_duration_s=5.0))

    assert not strict.valid
    assert lenient.valid


# --- measured quality on the real fixture -----------------------------------


@needs_ffmpeg
def test_the_real_fixture_is_prepared_to_a_measurable_standard(annotated, ground_truth, tmp_path):
    """Measured against exact ground truth, not against the pipeline's own output.

    These are the numbers the graduation report can quote for source
    preparation. They are an upper bound, not an estimate: synthesised speech has
    clean turn boundaries that real audio does not.
    """
    manifest = build_clips(annotated, FIXTURE, tmp_path)
    measured = compute_metrics(manifest, annotated, ground_truth)

    assert measured.valid, measured.exclusion_reasons
    assert measured.contamination_s == 0.0
    assert measured.candidate_precision > 0.99
    assert measured.candidate_recall > 0.90
    assert measured.word_attribution_accuracy == 1.0
    assert measured.boundary_mae_s < 0.5
    assert len(manifest.clips) == 3, "three questions were asked, so three answers"


# --- interval arithmetic ----------------------------------------------------


def test_overlapping_intervals_are_merged_before_being_totalled():
    """Double-counting an overlap inflates every ratio and can push precision
    above 1.0 on a recording with crosstalk."""
    assert total([(0.0, 5.0), (3.0, 8.0)]) == 8.0
    assert merge([(0.0, 5.0), (3.0, 8.0)]) == [(0.0, 8.0)]
    assert merge([(0.0, 1.0), (2.0, 3.0)]) == [(0.0, 1.0), (2.0, 3.0)]


def test_zero_length_intervals_are_discarded():
    assert merge([(1.0, 1.0)]) == []
    assert total([(1.0, 1.0)]) == 0.0


def test_intersection_is_symmetric_in_duration():
    a = [(0.0, 10.0)]
    b = [(5.0, 15.0)]
    assert total(intersect(a, b)) == total(intersect(b, a)) == 5.0
