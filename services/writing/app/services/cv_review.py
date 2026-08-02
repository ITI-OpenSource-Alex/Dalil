"""LLM review of an already-extracted CV."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import redis.asyncio as redis

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from goa_security import wrap_untrusted

from app.agents import _json_object, _response_text
from app.config import Settings, get_settings


logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 24 * 60 * 60
REVIEW_TIMEOUT_SECONDS = 120.0
REVIEW_SECTION_NAMES = (
    "Structure/Formatting",
    "Skills Gaps",
    "ATS Keywords",
    "Length Appropriateness",
    "Country Conventions",
)

_redis_client = None


class CVReviewSectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CVReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overallScore: int = Field(ge=0, le=100)
    sections: list[CVReviewSectionOutput] = Field(min_length=4)


@dataclass(frozen=True)
class CVReviewExecution:
    review: CVReviewOutput
    from_cache: bool
    cache_key: str


def review_cache_key(cv_text: str, target_country: str, target_field: str) -> str:
    canonical = f"{cv_text}\u001f{target_country}\u001f{target_field}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.environ.get("REDIS_GATEWAY_URL", "redis://redis-gateway:6379/0")
        _redis_client = redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
    return _redis_client


async def _read_cached_review(cache_key: str) -> CVReviewOutput | None:
    try:
        cached = await _get_redis_client().get(cache_key)
    except Exception as exc:
        logger.warning("cv_review_cache_read_failed", error=str(exc))
        return None
    if not cached:
        return None
    try:
        return CVReviewOutput.model_validate_json(cached)
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("cv_review_cache_invalid", error=str(exc))
        return None


async def _write_cached_review(cache_key: str, review: CVReviewOutput) -> None:
    try:
        await _get_redis_client().setex(
            cache_key,
            CACHE_TTL_SECONDS,
            review.model_dump_json(by_alias=True, exclude_none=True),
        )
    except Exception as exc:
        logger.warning("cv_review_cache_write_failed", error=str(exc))


async def _fetch_country_conventions(target_country: str, settings: Settings) -> dict[str, Any]:
    base_url = settings.rag_service_url.rstrip("/")
    headers = {}
    if settings.internal_api_key:
        headers["X-Internal-Api-Key"] = settings.internal_api_key

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{base_url}/internal/cv-country-conventions/{quote(target_country)}",
            headers=headers,
        )

    if response.status_code == 404:
        return {}
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        return payload
    return {"data": payload}


def _build_input(
    extracted_text: str | None,
    structured_data: dict[str, Any] | None,
    target_country: str,
    target_field: str,
    conventions: dict[str, Any],
) -> str:
    parts = [
        "You are reviewing a CV for a student or graduate applying for study or entry-level work abroad.",
        "Return only JSON matching this exact shape:",
        json.dumps(
            {
                "overallScore": 82,
                "sections": [
                    {
                        "name": "Structure/Formatting",
                        "score": 80,
                        "issues": ["..."],
                        "suggestions": ["..."]
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "Use exactly these section names in this order: " + ", ".join(REVIEW_SECTION_NAMES),
        f"Target country: {target_country}",
        f"Target field: {target_field}",
        # GOA-034. These conventions are retrieved by RAG from scraped pages, so
        # they are the same indirect-injection surface the RAG query path had:
        # content nobody here wrote, arriving with the standing of an instruction
        # unless it is marked otherwise. GOA-025 added this interpolation after
        # the fencing pass, so it is fenced on merge rather than left as a known
        # hole in a path this ticket already covers.
        wrap_untrusted(
            json.dumps(conventions, indent=2, ensure_ascii=False),
            label="COUNTRY CONVENTIONS",
            origin="pages scraped from the public web and retrieved by the RAG service",
        ),
    ]
    if structured_data:
        parts.append(
            "Structured data extracted from the CV:\n"
            + json.dumps(structured_data, indent=2, ensure_ascii=False)
        )
    if extracted_text:
        # Truncated because a CV is short and the tail of a long PDF is usually
        # references or boilerplate. Sending an unbounded document to the model
        # would make cost a function of whatever the user uploaded.
        #
        # GOA-034: fenced as untrusted. A CV is a file the user chose, and text
        # in a PDF can be invisible to a human reader -- white on white, or
        # sized to nothing -- while being perfectly legible to the model that
        # reads the extracted layer. That makes an uploaded document a better
        # injection vector than the chat box, not a worse one.
        parts.append(
            wrap_untrusted(
                extracted_text[:20000],
                label="RAW CV TEXT",
                origin="a document uploaded by the user",
            )
        )
    return "\n\n".join(parts)


def _build_client(settings: Settings) -> AsyncAnthropic:
    key = settings.anthropic_api_key or "not-configured"
    if key == "not-configured":
        logger.warning("ANTHROPIC_API_KEY is not configured; CV review will fail")
    client_kwargs: dict[str, Any] = {
        "api_key": key,
        "timeout": REVIEW_TIMEOUT_SECONDS,
        "max_retries": 1,
        "default_headers": {"User-Agent": settings.anthropic_user_agent},
    }
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url
    return AsyncAnthropic(**client_kwargs)


async def _generate_review(
    extracted_text: str | None,
    structured_data: dict[str, Any] | None,
    target_country: str,
    target_field: str,
    *,
    conventions: dict[str, Any],
    settings: Settings,
) -> CVReviewOutput:
    client = _build_client(settings)
    prompt = _build_input(
        extracted_text,
        structured_data,
        target_country,
        target_field,
        conventions,
    )

    last_error: Exception | None = None
    for attempt in range(2):
        messages = [{"role": "user", "content": prompt}]
        if attempt:
            messages = [
                {
                    "role": "user",
                    "content": (
                        "Your previous answer was not valid JSON for the required schema. "
                        "Return only the corrected JSON object.\n\n" + prompt
                    ),
                }
            ]
        response = await client.messages.create(
            model=settings.cv_review_model,
            max_tokens=2500,
            system=(
                "You are a careful CV review agent. Assess structure/formatting, "
                "skills gaps for the target field, ATS keyword optimisation, length "
                "appropriateness, and country-specific conventions. Give each section "
                "a 0-100 score. Return JSON only."
            ),
            messages=messages,
        )
        try:
            review = CVReviewOutput.model_validate_json(_json_object(_response_text(response)))
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            continue

        if {section.name for section in review.sections} >= set(REVIEW_SECTION_NAMES):
            return review
        last_error = ValueError("CV review did not return the required section set")

    raise ValueError("CV review model returned invalid JSON twice") from last_error


async def review_cv(
    extracted_text: str | None,
    structured_data: dict[str, Any] | None,
    target_country: str,
    target_field: str,
    *,
    settings: Settings | None = None,
) -> CVReviewExecution:
    settings = settings or get_settings()
    cache_key = review_cache_key(extracted_text or "", target_country, target_field)

    cached = await _read_cached_review(cache_key)
    if cached is not None:
        return CVReviewExecution(review=cached, from_cache=True, cache_key=cache_key)

    conventions = await _fetch_country_conventions(target_country, settings)
    review = await _generate_review(
        extracted_text,
        structured_data,
        target_country,
        target_field,
        conventions=conventions,
        settings=settings,
    )
    await _write_cached_review(cache_key, review)
    return CVReviewExecution(review=review, from_cache=False, cache_key=cache_key)
