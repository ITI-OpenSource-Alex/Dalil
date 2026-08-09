"""SPEAK-EVAL-005 acceptance tests: Gladia ingestion and role review.

Each acceptance criterion from the ticket gets a test that would fail if the
property were removed:

  - re-ingesting the same item/config reuses the prior completed job/artifact;
  - provider failure cannot create a partial canonical source silently;
  - `speaker 0` is never automatically treated as candidate;
  - raw and normalized artifacts are hash-linked;
  - no API key appears in logs/snapshots.

Everything here runs offline against the committed cassette, which was recorded
from a real Gladia response. Nothing in this file needs a key or a network.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from evals.providers.base import (
    GLADIA_KEY_HEADER,
    ProviderError,
    RequestProfile,
    RetryClass,
    idempotency_key,
    media_hash,
    redact,
)
from evals.providers.cassette import CassetteProvider
from evals.providers.gladia import GladiaProvider, classify_status
from evals.speaking.ingest import normalize as normalize_mod
from evals.speaking.ingest.normalize import ROLE_UNRESOLVED, normalize_gladia
from evals.speaking.ingest.roles import (
    RoleAnnotation,
    RoleAnnotationError,
    apply_roles,
    candidate_utterances,
    new_annotation,
    validate_annotation,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "evals" / "speaking" / "fixtures" / "two_speaker_part1.wav"
CASSETTES = REPO / "evals" / "providers" / "cassettes"

FAKE_KEY = "sk_gladia_thisisafakekeyfortests000000000"


@pytest.fixture
def profile() -> RequestProfile:
    return RequestProfile()


@pytest.fixture
def result(profile):
    return CassetteProvider().transcribe(FIXTURE, profile, item_id="smoke-two-speaker")


@pytest.fixture
def transcript(result):
    return normalize_gladia(
        result.raw,
        item_id="smoke-two-speaker",
        job_id=result.job_id,
        idempotency_key=result.idempotency_key,
        raw_sha256=result.raw_sha256(),
        request_profile_hash=result.identity.request_profile_hash,
        external_docs_reviewed_at=result.identity.external_docs_reviewed_at,
        audio_duration_s=result.audio_duration_s,
    )


# --- acceptance: re-ingestion reuses the prior artifact ---------------------


def test_reingesting_the_same_item_and_config_reuses_the_cassette(profile):
    """No second provider call, and the same bytes back.

    This is a correctness property before it is a cost one: a benchmark whose
    reference transcripts change between runs is not a benchmark.
    """
    provider = CassetteProvider()
    assert provider.has(FIXTURE, profile)

    first = provider.transcribe(FIXTURE, profile, item_id="smoke-two-speaker")
    second = provider.transcribe(FIXTURE, profile, item_id="smoke-two-speaker")

    assert first.job_id == second.job_id
    assert first.raw_sha256() == second.raw_sha256()
    assert first.idempotency_key == second.idempotency_key


def test_a_changed_config_is_a_different_job(profile):
    """Reusing a no-diarization result for a diarization request would return a
    transcript with no speaker labels and no indication anything was wrong."""
    other = RequestProfile(diarization=False)

    assert profile.config_hash() != other.config_hash()
    key_a = idempotency_key(media_hash(FIXTURE), profile)
    key_b = idempotency_key(media_hash(FIXTURE), other)
    assert key_a != key_b

    provider = CassetteProvider()
    assert provider.has(FIXTURE, profile)
    assert not provider.has(FIXTURE, other)


def test_a_cassette_miss_does_not_silently_call_the_provider(tmp_path, profile):
    """The CI configuration. A renamed fixture must fail loudly, not start
    spending money."""
    provider = CassetteProvider(cassette_dir=tmp_path)

    with pytest.raises(ProviderError) as excinfo:
        provider.transcribe(FIXTURE, profile, item_id="not-recorded")

    assert excinfo.value.retry_class is RetryClass.PERMANENT
    assert "no cassette" in str(excinfo.value)


# --- acceptance: a provider failure creates nothing -------------------------


def test_a_failed_job_raises_rather_than_returning_a_partial_result(profile):
    """A half-ingested source that looks complete is worse than a failed one."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://x.invalid/a.wav"})
        if request.url.path == "/v2/pre-recorded":
            return httpx.Response(201, json={"id": "job-1", "result_url": "https://x.invalid/r"})
        return httpx.Response(200, json={"status": "error", "error_code": "invalid_audio"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GladiaProvider(api_key=FAKE_KEY, client=client, allow_live=True, sleep=lambda _: None)

    with pytest.raises(ProviderError) as excinfo:
        provider.transcribe(FIXTURE, profile, item_id="doomed")

    assert excinfo.value.retry_class is RetryClass.INVALID_MEDIA
    assert "invalid_audio" in str(excinfo.value)


def test_an_unknown_status_is_refused_rather_than_polled_forever(profile):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://x.invalid/a.wav"})
        if request.url.path == "/v2/pre-recorded":
            return httpx.Response(201, json={"id": "job-1"})
        return httpx.Response(200, json={"status": "something_new"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GladiaProvider(api_key=FAKE_KEY, client=client, allow_live=True, sleep=lambda _: None)

    with pytest.raises(ProviderError, match="unknown status"):
        provider.transcribe(FIXTURE, profile, item_id="weird")


def test_live_calls_are_refused_unless_explicitly_enabled(profile):
    """The default must not cost money."""
    provider = GladiaProvider(api_key=FAKE_KEY, allow_live=False)

    with pytest.raises(ProviderError, match="live provider calls are disabled"):
        provider.transcribe(FIXTURE, profile, item_id="x")


@pytest.mark.parametrize(
    "status_code, expected",
    [
        (429, RetryClass.THROTTLED),
        (500, RetryClass.TRANSIENT),
        (503, RetryClass.TRANSIENT),
        (400, RetryClass.INVALID_MEDIA),
        (422, RetryClass.INVALID_MEDIA),
        # Retrying an invalid key nine times does not make it valid, and
        # repeated auth failures are what lockouts are built to detect.
        (401, RetryClass.PERMANENT),
        (403, RetryClass.PERMANENT),
    ],
)
def test_failures_are_classified_so_retrying_can_be_decided(status_code, expected):
    assert classify_status(status_code) is expected


def test_transient_errors_are_retried_and_counted(profile):
    calls = {"poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://x.invalid/a.wav"})
        if request.url.path == "/v2/pre-recorded":
            return httpx.Response(201, json={"id": "job-1"})
        calls["poll"] += 1
        if calls["poll"] <= 2:
            return httpx.Response(503, json={"message": "upstream busy"})
        return httpx.Response(200, json={"status": "done", "result": {
            "transcription": {"utterances": []}, "metadata": {"audio_duration": 1.0}
        }})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GladiaProvider(api_key=FAKE_KEY, client=client, allow_live=True, sleep=lambda _: None)

    outcome = provider.transcribe(FIXTURE, profile, item_id="flaky")
    assert outcome.retries == 2


# --- acceptance: speaker 0 is never automatically the candidate -------------


def test_normalisation_assigns_no_roles_at_all(transcript):
    """Every utterance comes out unresolved, whatever the speaker number."""
    assert transcript.provider_speakers == [0, 1]
    assert all(u.role == ROLE_UNRESOLVED for u in transcript.utterances)


def test_speaker_zero_is_the_examiner_in_the_real_recording(transcript):
    """The reason the rule exists, demonstrated on real provider output.

    Speaker 0 speaks first because the examiner asks the first question. A
    pipeline that mapped `speaker == 0` to candidate would score the interviewer
    on this item -- and on essentially every real IELTS recording, since they all
    open the same way.
    """
    first = min(transcript.utterances, key=lambda u: u.start_s)
    assert first.provider_speaker == 0
    assert "hometown" in " ".join(
        u.normalized_text for u in transcript.utterances if u.provider_speaker == 0
    ).lower()

    by_speaker = {}
    for u in transcript.utterances:
        by_speaker.setdefault(u.provider_speaker, 0.0)
        by_speaker[u.provider_speaker] += u.duration_s

    # The candidate speaks far longer than the examiner. Speaker 0 does not.
    assert by_speaker[1] > by_speaker[0] * 2


def test_extracting_candidate_speech_without_a_review_is_an_error(transcript):
    with pytest.raises(RoleAnnotationError, match="no utterance is assigned"):
        candidate_utterances(transcript)


def test_an_annotation_missing_a_speaker_is_rejected(transcript):
    annotation = new_annotation(transcript)
    annotation.speaker_roles = {"1": "candidate"}

    problems = validate_annotation(annotation, transcript)
    assert any("speaker 0 has no role assigned" in p for p in problems)


def test_two_candidates_are_rejected(transcript):
    annotation = new_annotation(transcript)
    annotation.speaker_roles = {"0": "candidate", "1": "candidate"}

    problems = validate_annotation(annotation, transcript)
    assert any("an IELTS item has exactly one" in p for p in problems)


def test_no_candidate_is_rejected(transcript):
    annotation = new_annotation(transcript)
    annotation.speaker_roles = {"0": "examiner", "1": "other"}

    problems = validate_annotation(annotation, transcript)
    assert any("nothing to score" in p for p in problems)


def test_a_gating_item_needs_two_reviewers(transcript):
    annotation = new_annotation(transcript)
    annotation.speaker_roles = {"0": "examiner", "1": "candidate"}
    annotation.reviewers = ["only-one"]
    annotation.reviewed_at = "2026-08-08T00:00:00+00:00"

    assert validate_annotation(annotation, transcript, for_gating=False) == []
    problems = validate_annotation(annotation, transcript, for_gating=True)
    assert any("needs 2 reviewers" in p for p in problems)


def test_applying_roles_leaves_the_normalised_transcript_untouched(transcript):
    annotation = new_annotation(transcript)
    annotation.speaker_roles = {"0": "examiner", "1": "candidate"}

    annotated = apply_roles(transcript, annotation)

    assert all(u.role == ROLE_UNRESOLVED for u in transcript.utterances)
    assert {u.role for u in annotated.utterances} == {"examiner", "candidate"}


def test_an_annotation_written_against_a_different_transcript_is_rejected(transcript):
    """A re-normalisation must invalidate the review rather than silently
    reapply a mapping made against different data."""
    annotation = new_annotation(transcript)
    annotation.speaker_roles = {"0": "examiner", "1": "candidate"}
    annotation.normalized_sha256 = "0" * 64

    problems = validate_annotation(annotation, transcript)
    assert any("different transcript" in p for p in problems)


# --- acceptance: raw and normalised are hash-linked -------------------------


def test_the_normalised_transcript_names_the_raw_response_it_came_from(result, transcript):
    assert transcript.raw_sha256 == result.raw_sha256()
    assert len(transcript.raw_sha256) == 64


def test_provenance_survives_normalisation(result, transcript):
    assert transcript.provider == "gladia"
    assert transcript.api_version == "v2"
    assert transcript.job_id == result.job_id
    assert transcript.idempotency_key == result.idempotency_key
    assert transcript.request_profile_hash == result.identity.request_profile_hash
    # A pinned date, so a future reader can tell how stale these assumptions are.
    assert transcript.external_docs_reviewed_at


def test_the_content_hash_changes_when_the_content_does(transcript):
    before = transcript.content_sha256()
    transcript.utterances[0].normalized_text += " tampered"
    assert transcript.content_sha256() != before


# --- acceptance: no API key in logs or snapshots ----------------------------


def test_no_committed_cassette_contains_a_credential():
    for cassette in CASSETTES.glob("*.json"):
        text = cassette.read_text(encoding="utf-8")
        assert "sk_gladia" not in text, f"{cassette.name} contains an API key"
        assert GLADIA_KEY_HEADER not in text.lower()


def test_signed_urls_are_stripped_before_a_cassette_is_written():
    """A signed audio_url is a bearer credential for the media and is usually
    valid for hours. It matters as much as the key."""
    payload = {
        "audio_url": "https://gladia.s3.amazonaws.com/x.wav?X-Amz-Signature=deadbeef",
        "headers": {GLADIA_KEY_HEADER: "sk_gladia_realkey"},
        "nested": [{"result_url": "https://api.gladia.io/v2/x?token=secret"}],
    }
    cleaned = redact(payload)

    assert "deadbeef" not in json.dumps(cleaned)
    assert "sk_gladia_realkey" not in json.dumps(cleaned)
    assert "secret" not in json.dumps(cleaned)
    assert cleaned["audio_url"].startswith("https://gladia.s3.amazonaws.com/x.wav")


def test_an_error_body_is_redacted_before_it_reaches_a_log(profile):
    """The adapter must not echo a request -- the request carries the key."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"message": "bad key", "echo": {GLADIA_KEY_HEADER: FAKE_KEY}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GladiaProvider(api_key=FAKE_KEY, client=client, allow_live=True, sleep=lambda _: None)

    with pytest.raises(ProviderError) as excinfo:
        provider.upload(FIXTURE)

    assert FAKE_KEY not in str(excinfo.value)
    assert "<redacted>" in str(excinfo.value)


def test_provider_metadata_carries_no_personal_data(profile):
    """Item id and idempotency key only.

    A band label sent to a transcription provider would also be a small leak of
    the answer key, quite apart from the privacy question.
    """
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/pre-recorded":
            captured.update(json.loads(request.content))
        return httpx.Response(201, json={"id": "job-1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GladiaProvider(api_key=FAKE_KEY, client=client, allow_live=True)
    provider.submit("https://x.invalid/a.wav", profile, item_id="item-7", key="k" * 64)

    assert set(captured["custom_metadata"]) == {"benchmark_item_id", "idempotency_key"}


# --- normalisation rejects rather than repairs -----------------------------


def _raw_with(utterances: list[dict], duration: float = 60.0) -> dict:
    return {
        "result": {
            "metadata": {"audio_duration": duration},
            "transcription": {"utterances": utterances},
        }
    }


def _normalize(raw: dict):
    return normalize_gladia(
        raw, item_id="t", job_id="j", idempotency_key="k", raw_sha256="h"
    )


@pytest.mark.parametrize(
    "utterance, fragment",
    [
        ({"start": 5.0, "end": 3.0, "speaker": 0, "text": "x"}, "negative duration"),
        ({"start": 1.0, "end": "later", "speaker": 0, "text": "x"}, "non-numeric"),
        ({"start": 1.0, "end": 900.0, "speaker": 0, "text": "x"}, "past the"),
        (
            {"start": 1.0, "end": 2.0, "speaker": 0, "text": "x",
             "words": [{"word": "a", "start": 0.1, "end": 0.2}]},
            "outside",
        ),
        (
            {"start": 1.0, "end": 2.0, "speaker": 0, "text": "x",
             "words": [{"word": "a", "start": 1.5, "end": 1.9},
                       {"word": "b", "start": 1.1, "end": 1.4}]},
            "not monotonic",
        ),
        (
            {"start": 1.0, "end": 2.0, "speaker": 0, "text": "x",
             "words": [{"word": "a", "start": 1.8, "end": 1.2}]},
            "negative duration",
        ),
    ],
)
def test_malformed_timings_are_quarantined_not_clipped(utterance, fragment):
    """Clipping a bad value to make schema validation pass destroys the evidence
    that anything was ever wrong."""
    transcript = _normalize(_raw_with([utterance]))

    assert not transcript.usable
    assert any(fragment in reason for reason in transcript.quarantine)


def test_overlapping_speech_is_flagged_not_silently_merged():
    transcript = _normalize(_raw_with([
        {"start": 1.0, "end": 5.0, "speaker": 0, "text": "first"},
        {"start": 4.0, "end": 8.0, "speaker": 1, "text": "interrupts"},
    ]))

    assert transcript.usable
    assert [u.overlap for u in transcript.utterances] == [False, True]


def test_a_response_with_no_transcription_is_an_error():
    with pytest.raises(normalize_mod.NormalizationError):
        _normalize({"result": {}})


def test_the_real_cassette_normalises_cleanly(transcript):
    assert transcript.usable
    assert transcript.quarantine == []
    assert len(transcript.utterances) == 21
    assert all(u.words for u in transcript.utterances)
