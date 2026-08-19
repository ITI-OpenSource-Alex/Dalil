"""Gladia V2 pre-recorded adapter (SPEAK-EVAL-005).

Implements the documented asynchronous lifecycle:

    POST /v2/upload          multipart, returns audio_url
    POST /v2/pre-recorded    returns job id and result_url
    GET  /v2/pre-recorded/{id}   poll until done or error

Live calls are OFF by default. `SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS` must be
explicitly true before this adapter will touch the network, because the default
that costs money on an accidental run is the wrong default.

Documented limits as reviewed on the date in EXTERNAL_DOCS_REVIEWED_AT: 135
minutes for ordinary pre-recorded audio, 1000 MB per file, 3 concurrent jobs on
free accounts and 25 on paid. Those are read from configuration rather than
hardcoded as constants, because they are account terms that change and a buried
constant is one nobody re-checks.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any

import httpx

from evals.providers.base import (
    GLADIA_KEY_HEADER,
    JobStatus,
    ProviderError,
    ProviderIdentity,
    RequestProfile,
    RetryClass,
    TranscriptionJob,
    TranscriptionResult,
    idempotency_key,
    media_hash,
    redact,
)

DEFAULT_BASE_URL = "https://api.gladia.io"
API_VERSION = "v2"

# The date the provider's documented limits, formats and concurrency were last
# read. Pinned into every artifact's provenance so a future reader can tell how
# stale these assumptions are, rather than assuming they are current.
EXTERNAL_DOCS_REVIEWED_AT = "2026-08-08"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def live_providers_allowed() -> bool:
    """Whether this process may make a paid provider call.

    Default false. An eval run that silently spends money because a key happened
    to be in the environment is a failure mode worth one boolean.
    """
    return os.environ.get("SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS", "").lower() in {
        "1",
        "true",
        "yes",
    }


def classify_status(status_code: int) -> RetryClass:
    """Map an HTTP status to a retry class.

    401/403 are PERMANENT rather than TRANSIENT deliberately: retrying an
    invalid key nine times does not make it valid, and repeated auth failures
    are what account lockouts are built to detect.
    """
    if status_code == 429:
        return RetryClass.THROTTLED
    if status_code in {400, 422}:
        return RetryClass.INVALID_MEDIA
    if status_code in {401, 402, 403, 404}:
        return RetryClass.PERMANENT
    if 500 <= status_code < 600:
        return RetryClass.TRANSIENT
    return RetryClass.PERMANENT


class GladiaProvider:
    """The live adapter. Costs money; requires a key and network."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        client: httpx.Client | None = None,
        allow_live: bool | None = None,
        sleep=time.sleep,
    ):
        self.api_key = api_key or os.environ.get("GLADIA_API_KEY", "")
        self.base_url = (base_url or os.environ.get("GLADIA_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.poll_initial_ms = _env_int("GLADIA_POLL_INITIAL_MS", 1000)
        self.poll_max_ms = _env_int("GLADIA_POLL_MAX_MS", 15000)
        self.job_timeout_s = _env_int("GLADIA_JOB_TIMEOUT_S", 900)
        self.max_concurrency = _env_int("GLADIA_MAX_CONCURRENCY", 2)
        self._client = client
        self._owns_client = client is None
        self._allow_live = live_providers_allowed() if allow_live is None else allow_live
        self._sleep = sleep

    # -- lifecycle ---------------------------------------------------------

    def identity(self, profile: RequestProfile) -> ProviderIdentity:
        return ProviderIdentity(
            provider="gladia",
            api_version=API_VERSION,
            request_profile_hash=profile.config_hash(),
            external_docs_reviewed_at=EXTERNAL_DOCS_REVIEWED_AT,
        )

    def transcribe(
        self,
        media_path: Path,
        profile: RequestProfile,
        *,
        item_id: str,
    ) -> TranscriptionResult:
        self._require_live()
        started = time.monotonic()

        key = idempotency_key(media_hash(media_path), profile)
        audio_url, upload_meta = self.upload(media_path)
        job = self.submit(audio_url, profile, item_id=item_id, key=key)
        raw, retries = self.poll(job)

        return TranscriptionResult(
            job_id=job.job_id,
            idempotency_key=key,
            identity=self.identity(profile),
            raw=raw,
            audio_duration_s=_audio_duration(raw) or upload_meta.get("audio_duration"),
            provider_latency_s=round(time.monotonic() - started, 3),
            retries=retries,
        )

    def upload(self, media_path: Path) -> tuple[str, dict[str, Any]]:
        """POST /v2/upload. Returns the audio_url and any reported metadata."""
        with media_path.open("rb") as handle:
            response = self._request(
                "POST",
                "/v2/upload",
                files={"audio": (media_path.name, handle, "application/octet-stream")},
            )
        payload = response.json()
        audio_url = payload.get("audio_url")
        if not audio_url:
            raise ProviderError(
                "upload succeeded but returned no audio_url", RetryClass.PERMANENT
            )
        return audio_url, payload.get("audio_metadata", {}) or {}

    def submit(
        self,
        audio_url: str,
        profile: RequestProfile,
        *,
        item_id: str,
        key: str,
    ) -> TranscriptionJob:
        """POST /v2/pre-recorded.

        `custom_metadata` carries the benchmark item id and the idempotency key
        and nothing else. No names, no URLs, no labels -- the plan is explicit
        that provider-side metadata is not a place for personal data, and a band
        label sent to a transcription provider would also be a small leak of the
        answer key.
        """
        body = profile.to_request()
        body["audio_url"] = audio_url
        body["custom_metadata"] = {
            "benchmark_item_id": item_id,
            "idempotency_key": key,
        }

        response = self._request("POST", "/v2/pre-recorded", json=body)
        payload = response.json()

        job_id = payload.get("id")
        if not job_id:
            raise ProviderError(
                "job submission returned no id", RetryClass.PERMANENT
            )
        return TranscriptionJob(
            job_id=job_id,
            idempotency_key=key,
            status=JobStatus.QUEUED,
            result_url=payload.get("result_url"),
        )

    def poll(self, job: TranscriptionJob) -> tuple[dict[str, Any], int]:
        """Poll until done or error, with exponential backoff and jitter.

        Jitter matters more than it looks: several items submitted together
        otherwise poll in lockstep forever, turning a concurrency limit into a
        synchronised burst against it.

        A job that ends in `error` raises. It must never return a partial
        result -- an ingestion that half-worked and looks complete is the
        failure this whole plane is built to avoid.
        """
        deadline = time.monotonic() + self.job_timeout_s
        delay_ms = self.poll_initial_ms
        retries = 0

        while True:
            if time.monotonic() > deadline:
                raise ProviderError(
                    f"job {job.job_id} did not finish within {self.job_timeout_s}s",
                    RetryClass.TRANSIENT,
                )

            try:
                response = self._request("GET", f"/v2/pre-recorded/{job.job_id}")
                payload = response.json()
            except ProviderError as exc:
                if exc.retry_class not in {RetryClass.TRANSIENT, RetryClass.THROTTLED}:
                    raise
                retries += 1
                self._backoff(delay_ms)
                delay_ms = min(delay_ms * 2, self.poll_max_ms)
                continue

            status = payload.get("status")

            if status == JobStatus.DONE.value:
                return payload, retries

            if status == JobStatus.ERROR.value:
                detail = payload.get("error_code") or payload.get("error") or "unknown"
                raise ProviderError(
                    f"job {job.job_id} failed: {detail}",
                    RetryClass.INVALID_MEDIA,
                )

            if status not in {JobStatus.QUEUED.value, JobStatus.PROCESSING.value}:
                raise ProviderError(
                    f"job {job.job_id} reported unknown status {status!r}",
                    RetryClass.PERMANENT,
                )

            self._backoff(delay_ms)
            delay_ms = min(delay_ms * 2, self.poll_max_ms)

    # -- plumbing ----------------------------------------------------------

    def _require_live(self) -> None:
        if not self._allow_live:
            raise ProviderError(
                "live provider calls are disabled. Set "
                "SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS=true to permit a paid Gladia "
                "call, or use CassetteProvider for replay.",
                RetryClass.PERMANENT,
            )
        if not self.api_key:
            raise ProviderError(
                "GLADIA_API_KEY is not set", RetryClass.PERMANENT
            )

    def _headers(self) -> dict[str, str]:
        return {GLADIA_KEY_HEADER: self.api_key}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        client = self._client or httpx.Client(timeout=120.0)
        try:
            response = client.request(
                method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
            )
        except httpx.HTTPError as exc:
            # Transport failures are transient by nature: no server ever saw
            # this request, so nothing about the account state has changed.
            raise ProviderError(f"{method} {path}: {exc}", RetryClass.TRANSIENT) from exc
        finally:
            if self._owns_client and self._client is None:
                client.close()

        if response.status_code >= 400:
            raise ProviderError(
                # response.text, never the request: the request carries the key.
                f"{method} {path}: {_safe_body(response)}",
                classify_status(response.status_code),
                status_code=response.status_code,
            )
        return response

    def _backoff(self, delay_ms: int) -> None:
        jitter = random.uniform(0.5, 1.5)
        self._sleep((delay_ms / 1000.0) * jitter)


def _safe_body(response: httpx.Response) -> str:
    """A bounded, redacted rendering of an error body for a log line."""
    try:
        return str(redact(response.json()))[:400]
    except Exception:
        return response.text[:400]


def _audio_duration(raw: dict[str, Any]) -> float | None:
    for path in (
        ("result", "metadata", "audio_duration"),
        ("metadata", "audio_duration"),
    ):
        node: Any = raw
        for key in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, (int, float)):
            return float(node)
    return None
