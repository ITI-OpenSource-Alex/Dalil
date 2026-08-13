"""Provider-neutral transcription contract for the benchmark ingestion plane.

SPEAK-EVAL-005. The boundary exists so that Gladia calls live in exactly one
file. The alternative -- `httpx.post("https://api.gladia.io/...")` scattered
through the runner -- makes three things impossible at once: replaying a
benchmark without paying for it, testing the error paths, and swapping the
provider later without touching the scoring code.

Two implementations sit behind this contract:

  GladiaProvider    talks to the real V2 pre-recorded API. Costs money, needs a
                    key, needs network.
  CassetteProvider  replays recorded responses. No key, no network, and the
                    default everywhere including CI.

Nothing above this module knows which one it has.

Note on what this plane is NOT. Gladia is used here to prepare *source* material
-- to work out which words the candidate said and when. It is deliberately not
wired into the product's speech sidecar. Keeping the reference transcription and
the system under test on separate providers is what lets a bad score be
attributed to scoring rather than to transcription; if both used Gladia, an
error common to both would be invisible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class JobStatus(str, Enum):
    """The documented V2 lifecycle states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class RetryClass(str, Enum):
    """What kind of failure this is, which decides whether retrying can help.

    Collapsing these into a single "failed" is how a dead credential comes to be
    retried nine times and how a genuinely transient 503 gets abandoned on the
    first attempt.
    """

    TRANSIENT = "transient"
    """Network blip, 502/503/504. Retry with backoff."""

    THROTTLED = "throttled"
    """429 or concurrency limit. Retry, more slowly."""

    INVALID_MEDIA = "invalid_media"
    """The file is not something the provider can process. Retrying cannot help."""

    PERMANENT = "permanent"
    """Auth failure, validation error, quota exhausted. Retrying cannot help and
    hammering an invalid key is how an account gets suspended."""


class ProviderError(RuntimeError):
    """A provider failure, carrying its retry classification."""

    def __init__(self, message: str, retry_class: RetryClass, status_code: int | None = None):
        super().__init__(message)
        self.retry_class = retry_class
        self.status_code = status_code

    def __str__(self) -> str:
        code = f" (HTTP {self.status_code})" if self.status_code else ""
        return f"[{self.retry_class.value}]{code} {super().__str__()}"


@dataclass(frozen=True)
class RequestProfile:
    """The versioned transcription settings, hashed into the idempotency key.

    Explicit and frozen rather than assembled at the call site: the settings a
    transcript was produced under are part of its provenance, and a setting that
    can drift between two runs makes those runs incomparable while looking
    identical in the report.

    Defaults follow section 7.3 of the plan -- diarization on, English, and every
    enrichment off. Enrichment is off because a summarisation or sentiment field
    the benchmark never reads is cost and a surface for surprises, not a feature.
    """

    diarization: bool = True
    number_of_speakers: int | None = 2
    language: str = "en"
    detect_language: bool = False
    enable_code_switching: bool = False

    # Enrichment, all off. Named individually rather than left absent so the
    # profile hash changes if a future version turns one on.
    translation: bool = False
    summarization: bool = False
    sentiment_analysis: bool = False
    audio_to_llm: bool = False
    moderation: bool = False
    named_entity_recognition: bool = False
    chapterization: bool = False

    # Free-form provider settings, for a documented option this dataclass does
    # not model yet. Included in the hash.
    extra: dict[str, Any] = field(default_factory=dict)

    def to_request(self) -> dict[str, Any]:
        """The provider request body, minus the audio_url."""
        body: dict[str, Any] = {
            "diarization": self.diarization,
            "detect_language": self.detect_language,
            "enable_code_switching": self.enable_code_switching,
            "translation": self.translation,
            "summarization": self.summarization,
            "sentiment_analysis": self.sentiment_analysis,
            "audio_to_llm": self.audio_to_llm,
            "moderation": self.moderation,
            "named_entity_recognition": self.named_entity_recognition,
            "chapterization": self.chapterization,
        }
        if self.diarization and self.number_of_speakers is not None:
            # Bounded rather than exact: a recording with an unexpected third
            # voice should surface as a review flag, not be forced into two.
            body["diarization_config"] = {
                "number_of_speakers": self.number_of_speakers,
                "min_speakers": 1,
                "max_speakers": max(self.number_of_speakers + 2, 4),
            }
        if not self.detect_language:
            body["language"] = self.language
        body.update(self.extra)
        return body

    def config_hash(self) -> str:
        """Stable hash of the settings.

        Half of the idempotency key. Two runs of the same audio under different
        settings are different transcriptions and must not reuse each other's
        result; two runs under the same settings are the same job and must not
        be paid for twice.
        """
        canonical = json.dumps(self.to_request(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderIdentity:
    """Who produced a transcript and under what version.

    Stored with every artifact. A transcript with no record of the provider and
    API version cannot be compared against one produced six months later, and
    the comparison will be attempted anyway unless the data makes it impossible.
    """

    provider: str
    api_version: str
    request_profile_hash: str
    external_docs_reviewed_at: str
    """The date the provider's documented limits and behaviour were last checked.
    Provider behaviour changes; a pinned date is what tells a future reader how
    stale this integration's assumptions are."""


@dataclass(frozen=True)
class TranscriptionJob:
    """A submitted job, before its result is known."""

    job_id: str
    idempotency_key: str
    status: JobStatus
    result_url: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    """A completed job: the raw response plus what it cost to get it.

    `raw` is the provider's response verbatim. It is stored before any
    normalisation, because normalisation is lossy and a normaliser bug found in
    three months can only be repaired if the original survived.
    """

    job_id: str
    idempotency_key: str
    identity: ProviderIdentity
    raw: dict[str, Any]

    audio_duration_s: float | None = None
    provider_latency_s: float | None = None
    retries: int = 0
    estimated_cost_usd: float | None = None

    def raw_sha256(self) -> str:
        """Content hash of the raw response, for hash-linking to the normalised form."""
        canonical = json.dumps(self.raw, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def media_hash(path: Path) -> str:
    """SHA-256 of a media file, streamed.

    The other half of the idempotency key, and the thing that makes "the same
    item" mean the same bytes rather than the same filename. A file renamed is
    the same job; a file re-encoded is not.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def idempotency_key(media_sha256: str, profile: RequestProfile) -> str:
    """Item hash plus configuration hash, per the plan.

    Deliberately not the item hash alone: re-running the same audio with
    diarization newly enabled must produce a new job, and reusing the old
    result would silently return a transcript with no speaker labels.
    """
    combined = f"{media_sha256}:{profile.config_hash()}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


class TranscriptionProvider(Protocol):
    """What the ingestion pipeline is allowed to depend on."""

    def identity(self, profile: RequestProfile) -> ProviderIdentity: ...

    def transcribe(
        self,
        media_path: Path,
        profile: RequestProfile,
        *,
        item_id: str,
    ) -> TranscriptionResult:
        """Upload, submit, poll, and return the completed raw result.

        Must raise ProviderError rather than returning a partial result. A
        half-ingested source that looks complete is worse than a failed
        ingestion, because the failure is visible and the half is not.
        """
        ...


# Header name kept here so both the adapter and the redaction tests reference one
# constant rather than two string literals that can drift apart.
GLADIA_KEY_HEADER = "x-gladia-key"


def redact(value: Any) -> Any:
    """Strip credentials and signed URLs from anything about to be logged or stored.

    Applied to headers, request bodies and provider responses before they reach a
    log line or a committed cassette. The signed `audio_url` matters as much as
    the key: it is a bearer credential for the media, it is often valid for
    hours, and it is the field most likely to be pasted into an issue.
    """
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {GLADIA_KEY_HEADER, "authorization", "x-api-key", "api_key"}:
                redacted[key] = "<redacted>"
            elif lowered in {"audio_url", "result_url", "url", "callback_url"}:
                redacted[key] = _redact_url(item)
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(entry) for entry in value]
    return value


def _redact_url(value: Any) -> Any:
    """Keep a URL recognisable without keeping it usable."""
    if not isinstance(value, str):
        return value
    if "?" in value:
        return value.split("?", 1)[0] + "?<redacted>"
    return value
