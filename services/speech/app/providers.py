"""Transcription providers behind the speech-service boundary (SPEAK-EVAL-011).

The Go speaking service posts audio to `/stt` and reads back a transcript, a
duration and words with timings. That contract is what this module exists to
protect: which engine produced those bytes is a decision inside this service,
not a fact the caller knows.

**The property that matters is negative.** The acceptance criterion is that the
Go speaking service does not become Gladia-coupled. Go must remain able to
compile, run and pass its tests with no knowledge that Gladia exists — no client,
no key, no branch on provider. If the provider ever leaks across `/stt`, the
experiment has failed regardless of which engine wins on accuracy, because the
next provider change becomes a change to a scoring service.

So selection is a sidecar-side configuration read, and the response carries the
provider in `provenance` rather than requiring the caller to ask for one.

**Local remains the default.** `SPEECH_PROVIDER` defaults to faster-whisper.
Gladia costs money per minute and sends candidate audio to a third party, and
neither should be entered by forgetting to set a variable.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """Transcription failed. Carries whether a retry could plausibly help."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Word:
    word: str
    start: float
    end: float
    # `probability`, matching what the sidecar has always emitted and what
    # agents.Word unmarshals. The name is part of the wire contract: a driver
    # that called it `confidence` sent every word through as 0.0 and the
    # Pronunciation agent was handed "mean confidence 0.00" for a perfectly
    # intelligible speaker (SPEAK-EVAL-007).
    probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "probability": round(self.probability, 4) if self.probability is not None else None,
        }


@dataclass
class Transcription:
    """Provider-neutral result. Shaped exactly like the existing /stt body."""

    transcript: str
    duration_s: float
    words: list[Word] = field(default_factory=list)
    language: str | None = None
    language_probability: float | None = None
    segments: list[dict[str, Any]] = field(default_factory=list)

    # Provenance of the transcription, not of the score. Recorded so a band can
    # be traced to the engine that produced the words underneath it -- two
    # sessions transcribed by different providers are not directly comparable.
    provider: str = "faster-whisper"
    provider_model: str | None = None
    provider_latency_ms: int | None = None
    estimated_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            # First and unchanged: an older client reading only this key keeps
            # working against a redeployed sidecar.
            "transcript": self.transcript,
            "duration_s": round(self.duration_s, 3),
            "language": self.language,
            "language_probability": (
                round(self.language_probability, 4)
                if self.language_probability is not None
                else None
            ),
            "segments": self.segments,
            "words": [w.to_dict() for w in self.words],
            "provenance": {
                "provider": self.provider,
                "model": self.provider_model,
                "latency_ms": self.provider_latency_ms,
                # None, never 0.0, when a provider is free or unpriced. "We did
                # not price this" and "this was free" are different facts
                # (GOA-135).
                "estimated_cost_usd": self.estimated_cost_usd,
            },
        }


class TranscriptionProvider(Protocol):
    name: str

    def transcribe(self, audio_path: str) -> Transcription: ...


# --- local ------------------------------------------------------------------


class FasterWhisperProvider:
    """The incumbent. Runs locally, costs nothing per minute, sends nothing out."""

    name = "faster-whisper"

    def __init__(self, model, model_size: str = "base"):
        self._model = model
        self._model_size = model_size

    def transcribe(self, audio_path: str) -> Transcription:
        started = time.monotonic()
        segments, info = self._model.transcribe(audio_path, word_timestamps=True)

        # Materialised once. `segments` is a generator, and a second pass over it
        # yields nothing -- which comes back as an empty words array for reasons
        # that look like a model problem.
        collected = list(segments)

        words = [
            Word(
                word=word.word,
                start=word.start,
                end=word.end,
                probability=word.probability,
            )
            for segment in collected
            for word in (segment.words or [])
        ]

        return Transcription(
            transcript="".join(segment.text for segment in collected).strip(),
            duration_s=info.duration,
            words=words,
            language=info.language,
            language_probability=info.language_probability,
            segments=[
                {
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "text": segment.text,
                }
                for segment in collected
            ],
            provider=self.name,
            provider_model=self._model_size,
            provider_latency_ms=int((time.monotonic() - started) * 1000),
            # Local inference has no per-minute price. None rather than 0.0
            # would imply we could not price it; 0.0 is the honest value here.
            estimated_cost_usd=0.0,
        )


# --- Gladia -----------------------------------------------------------------

# Published rate at the time of writing, per audio hour. Configurable because it
# is a commercial term that changes, and a buried constant is one nobody
# re-checks.
GLADIA_USD_PER_HOUR = float(os.getenv("GLADIA_USD_PER_HOUR", "0.612"))


class GladiaProvider:
    """The experiment. Costs money per minute and sends audio to a third party.

    Deliberately thin: it reuses the adapter already written and exercised for
    the benchmark ingestion plane (`evals/providers/gladia.py`) rather than
    growing a second Gladia client. Two clients for one API is how two
    behaviours for one API begin.
    """

    name = "gladia"

    def __init__(self, adapter, profile):
        self._adapter = adapter
        self._profile = profile

    def transcribe(self, audio_path: str) -> Transcription:
        from pathlib import Path

        started = time.monotonic()
        try:
            result = self._adapter.transcribe(
                Path(audio_path), self._profile, item_id="production"
            )
        except Exception as exc:
            # Wrapped, so a caller of this module never has to know which
            # provider's exception type it is catching.
            raise ProviderError(f"gladia transcription failed: {exc}", retryable=True) from exc

        return normalise_gladia(
            result.raw,
            latency_ms=int((time.monotonic() - started) * 1000),
        )


def normalise_gladia(raw: dict[str, Any], *, latency_ms: int | None = None) -> Transcription:
    """Map a Gladia V2 response onto the sidecar's shape.

    Kept a free function so it can be tested against a recorded response with no
    network, no key and no adapter.
    """
    result = raw.get("result") or {}
    transcription = result.get("transcription") or {}
    metadata = result.get("metadata") or {}
    utterances = transcription.get("utterances") or []

    words: list[Word] = []
    segments: list[dict[str, Any]] = []

    for utterance in utterances:
        segments.append(
            {
                "start": round(float(utterance.get("start", 0.0)), 3),
                "end": round(float(utterance.get("end", 0.0)), 3),
                "text": utterance.get("text", ""),
            }
        )
        for word in utterance.get("words") or []:
            words.append(
                Word(
                    word=word.get("word", ""),
                    start=float(word.get("start", 0.0)),
                    end=float(word.get("end", 0.0)),
                    # Gladia calls it `confidence`; the sidecar contract calls it
                    # `probability`. Translated HERE, at the boundary, which is
                    # the only place that knows both names.
                    probability=word.get("confidence"),
                )
            )

    duration = float(metadata.get("audio_duration") or 0.0)

    return Transcription(
        transcript=(transcription.get("full_transcript") or "").strip(),
        duration_s=duration,
        words=words,
        language=(transcription.get("languages") or [None])[0],
        segments=segments,
        provider="gladia",
        provider_model="gladia-v2",
        provider_latency_ms=latency_ms,
        estimated_cost_usd=round(duration / 3600.0 * GLADIA_USD_PER_HOUR, 6) if duration else None,
    )


# --- selection --------------------------------------------------------------


def configured_provider_name() -> str:
    """Which provider this sidecar is configured to use.

    Defaults to the local engine. Gladia costs money per minute and sends
    candidate audio to a third party; neither is a state to enter by forgetting
    to set a variable.
    """
    return (os.getenv("SPEECH_PROVIDER") or "faster-whisper").strip().lower()


def build_provider(*, whisper_model, whisper_size: str = "base"):
    """Construct the configured provider.

    Falls back to local with a loud warning rather than failing the service: a
    sidecar that refuses to start because an experimental provider is
    misconfigured has turned an optional experiment into an outage.
    """
    name = configured_provider_name()

    if name in ("faster-whisper", "local", "whisper"):
        return FasterWhisperProvider(whisper_model, whisper_size)

    if name == "gladia":
        try:
            from evals.providers.base import RequestProfile
            from evals.providers.gladia import GladiaProvider as GladiaAdapter

            adapter = GladiaAdapter()
            # Diarization off: the sidecar transcribes one candidate clip at a
            # time. Speaker separation belongs to the offline ingestion plane,
            # where a human reviews the roles.
            profile = RequestProfile(diarization=False, number_of_speakers=None)
            return GladiaProvider(adapter, profile)
        except Exception as exc:  # pragma: no cover - configuration path
            import logging

            logging.getLogger(__name__).error(
                "SPEECH_PROVIDER=gladia could not be constructed (%s); "
                "falling back to faster-whisper. The sidecar stays up: an "
                "experimental provider must not be able to cause an outage.",
                exc,
            )
            return FasterWhisperProvider(whisper_model, whisper_size)

    import logging

    logging.getLogger(__name__).warning(
        "Unknown SPEECH_PROVIDER=%r; using faster-whisper.", name
    )
    return FasterWhisperProvider(whisper_model, whisper_size)
