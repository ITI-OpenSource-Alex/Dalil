"""Cassette provider: replay recorded provider responses (SPEAK-EVAL-005).

The default provider everywhere, including CI. No key, no network, no cost.

Two jobs, and the second is the one that matters:

1. Let the ingestion pipeline be tested end to end without a paid API.
2. Make re-ingestion of an already-ingested item **reuse** the stored artifact
   rather than calling the provider again. That is the ticket's first acceptance
   criterion, and it is a correctness property as much as a cost one: a
   benchmark whose reference transcripts silently change between runs is not a
   benchmark.

Cassettes are keyed by idempotency key -- media hash plus config hash -- so the
same audio under different settings correctly misses the cache.

A cassette is recorded from a real response and then committed, so what CI
replays is what the provider actually said, not what someone imagined it would
say. Recording runs `redact()` over the payload first: a committed cassette that
carries a signed audio_url is a credential in the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.providers.base import (
    ProviderError,
    ProviderIdentity,
    RequestProfile,
    RetryClass,
    TranscriptionResult,
    idempotency_key,
    media_hash,
    redact,
)

DEFAULT_CASSETTE_DIR = Path(__file__).resolve().parent / "cassettes"


class CassetteProvider:
    """Replays a stored response for a known idempotency key."""

    def __init__(
        self,
        cassette_dir: Path | None = None,
        *,
        record_with: Any = None,
    ):
        """
        record_with: an optional live provider. When supplied, a cache miss
        performs a real transcription and writes the cassette. When absent --
        the CI configuration -- a miss is an error, so a test can never silently
        start making paid network calls because a fixture was renamed.
        """
        self.cassette_dir = cassette_dir or DEFAULT_CASSETTE_DIR
        self._record_with = record_with

    def identity(self, profile: RequestProfile) -> ProviderIdentity:
        if self._record_with is not None:
            return self._record_with.identity(profile)
        return ProviderIdentity(
            provider="gladia",
            api_version="v2",
            request_profile_hash=profile.config_hash(),
            external_docs_reviewed_at="2026-08-08",
        )

    def path_for(self, key: str) -> Path:
        return self.cassette_dir / f"{key[:32]}.json"

    def has(self, media_path: Path, profile: RequestProfile) -> bool:
        return self.path_for(idempotency_key(media_hash(media_path), profile)).exists()

    def transcribe(
        self,
        media_path: Path,
        profile: RequestProfile,
        *,
        item_id: str,
    ) -> TranscriptionResult:
        key = idempotency_key(media_hash(media_path), profile)
        cassette = self.path_for(key)

        if cassette.exists():
            return self._load(cassette, key)

        if self._record_with is None:
            raise ProviderError(
                f"no cassette for item {item_id!r} (key {key[:12]}...) and recording "
                f"is disabled. Re-record with GLADIA_API_KEY and "
                f"SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS=true, or check the media has "
                f"not changed under its manifest hash.",
                RetryClass.PERMANENT,
            )

        result = self._record_with.transcribe(media_path, profile, item_id=item_id)
        self._save(cassette, result, item_id=item_id)
        return result

    # -- storage -----------------------------------------------------------

    def _load(self, cassette: Path, key: str) -> TranscriptionResult:
        with cassette.open(encoding="utf-8") as handle:
            stored = json.load(handle)

        identity = stored["identity"]
        return TranscriptionResult(
            job_id=stored["job_id"],
            idempotency_key=key,
            identity=ProviderIdentity(
                provider=identity["provider"],
                api_version=identity["api_version"],
                request_profile_hash=identity["request_profile_hash"],
                external_docs_reviewed_at=identity["external_docs_reviewed_at"],
            ),
            raw=stored["raw"],
            audio_duration_s=stored.get("audio_duration_s"),
            # The replayed latency is the recording's, not this run's. Kept so a
            # report can state what the provider actually took, and clearly not
            # a measurement of the replay.
            provider_latency_s=stored.get("provider_latency_s"),
            retries=stored.get("retries", 0),
            estimated_cost_usd=stored.get("estimated_cost_usd"),
        )

    def _save(self, cassette: Path, result: TranscriptionResult, *, item_id: str) -> None:
        cassette.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "recorded_for_item": item_id,
            "job_id": result.job_id,
            "idempotency_key": result.idempotency_key,
            "identity": {
                "provider": result.identity.provider,
                "api_version": result.identity.api_version,
                "request_profile_hash": result.identity.request_profile_hash,
                "external_docs_reviewed_at": result.identity.external_docs_reviewed_at,
            },
            "audio_duration_s": result.audio_duration_s,
            "provider_latency_s": result.provider_latency_s,
            "retries": result.retries,
            "estimated_cost_usd": result.estimated_cost_usd,
            # Redacted before it touches disk. A cassette is committed, and a
            # signed audio_url in a committed file is a credential in the repo.
            "raw": redact(result.raw),
        }
        with cassette.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
