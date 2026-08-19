"""CV review agent for GOA-025.

The endpoint reviews CV text that the CV processor already extracted. It does
not parse files, re-fetch S3, or mutate the extracted CV row.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Awaitable, Callable

import httpx
from pydantic import BaseModel, Field

from goa_security import wrap_untrusted

from app.agents import _json_object, _response_text
from app.config import Settings, get_settings
from app.schemas import CVReviewResponse, CVReviewSection

logger = logging.getLogger(__name__)

REVIEW_MODEL = "claude-opus-5"
REVIEW_TIMEOUT_SECONDS = 120.0
REVIEW_REQUEST_TIMEOUT_SECONDS = 120.0
COUNTRY_CONVENTIONS_TIMEOUT_SECONDS = 3.0
# The router may emit a ThinkingBlock before its TextBlock. One response now
# contains all five concise sections, so it needs enough output room for both.
REVIEW_MAX_TOKENS = 6000
CACHE_TTL_SECONDS = 24 * 60 * 60
SECTION_NAMES: tuple[str, ...] = (
    "Structure and formatting",
    "Skills gaps",
    "ATS keyword optimization",
    "Length appropriateness",
    "Country-specific conventions",
)


class RawCVSection(BaseModel):
    name: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class RawCVReview(BaseModel):
    sections: list[RawCVSection] = Field(min_length=1, max_length=5)


@dataclass(frozen=True)
class CVSectionExecution:
    result: CVReviewSection
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class CVReviewExecution:
    sections: list[CVReviewSection]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class CVReviewSummary:
    overall_score: int
    sections: list[CVReviewSection]
    total_tokens: int


PartialCallback = Callable[[CVReviewSection], Awaitable[None] | None]


def cv_review_cache_key(
    cv_text: str,
    target_country: str,
    target_field: str,
    settings: Settings,
    program_context: dict[str, Any] | None = None,
) -> str:
    payload = json.dumps(
        {
            "version": settings.cache_version,
            "cvText": cv_text,
            "targetCountry": target_country.strip().casefold(),
            "targetField": target_field.strip().casefold(),
            "programContext": program_context or {},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "cv-review:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_cv_context(
    extracted_text: str | None,
    structured_data: dict[str, Any] | None,
) -> str:
    parts = []

    if structured_data:
        parts.append(
            "Structured CV data:\n"
            + json.dumps(structured_data, ensure_ascii=False, indent=2)
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
                label="EXTRACTED CV TEXT",
                origin="a document uploaded by the user",
            )
        )
    return "\n\n".join(parts)


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _notify(callback: PartialCallback | None, result: CVReviewSection) -> None:
    if callback is None:
        return
    await maybe_await(callback(result))


async def fetch_country_conventions(
    user_id: str,
    target_country: str,
    settings: Settings,
) -> str:
    question = (
        "Summarize country-specific CV conventions for a student applying in "
        f"{target_country}. Include photo expectations, length, personal details, "
        "format, Europass or local convention guidance, and any ATS implications."
    )
    try:
        # This lookup is supplemental context. Programme requirements are already
        # supplied separately, so a slow RAG answer must not hold the visible
        # review in a loading state before any section work can begin.
        async with httpx.AsyncClient(
            timeout=COUNTRY_CONVENTIONS_TIMEOUT_SECONDS,
        ) as client:
            response = await client.post(
                f"{settings.rag_service_url.rstrip('/')}/query",
                json={"userId": user_id, "question": question, "topK": 5},
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.warning(
            "RAG country CV conventions lookup failed",
            exc_info=True,
            extra={"target_country": target_country},
        )
        return (
            "No RAG convention documents were available. Apply conservative, widely "
            "accepted country-specific CV guidance and call out uncertainty."
        )
    return str(data.get("answer") or "").strip()


class CVReviewRunner:
    def __init__(self, client: Any, *, model: str = REVIEW_MODEL) -> None:
        self.client = client
        self.model = model

    async def review_section(
        self,
        section_name: str,
        *,
        cv_context: str,
        target_country: str,
        target_field: str,
        country_conventions: str,
        program_context: dict[str, Any] | None = None,
    ) -> CVSectionExecution:
        system = (
            "You are the GOA CV Review Agent. Review one CV section dimension "
            "against study-abroad admissions, target-field expectations, ATS "
            "keyword quality, and country-specific conventions. Return only JSON. "
            "Do not include reasoning, thinking blocks, markdown, or commentary; "
            "start immediately with the JSON object."
        )
        # GOA-034. These conventions are summarised by RAG from scraped pages,
        # so they are the same indirect-injection surface the RAG query path
        # had: content nobody here wrote, interpolated into a prompt with the
        # standing of an instruction unless it is marked otherwise. GOA-025
        # added this interpolation after the fencing pass, so it is fenced on
        # merge rather than left as a known hole in a file this ticket covers.
        fenced_conventions = wrap_untrusted(
            country_conventions[:4000],
            label="COUNTRY CONVENTION CONTEXT",
            origin="pages scraped from the public web and summarised by the RAG service",
        )
        fenced_program = wrap_untrusted(
            json.dumps(program_context or {}, ensure_ascii=False, indent=2)[:6000],
            label="SELECTED PROGRAMME REQUIREMENTS",
            origin="the programme catalogue owned by the RAG service",
        )
        prompt = f"""Return one JSON object with this exact shape:
{{
  "name": "{section_name}",
  "score": 0,
  "issues": ["specific problems found"],
  "suggestions": ["specific improvements the candidate can make"]
}}

Rules:
- score is an integer from 0 to 100.
- Judge only the supplied extracted CV content; do not invent credentials.
- If the skills section is absent, the Skills gaps section must explicitly say so.
- Suggestions must be concrete rewrite or content actions.
- Country conventions matter for {target_country}; e.g. photo expectations can differ by country.

Target country: {target_country}
Target field: {target_field}
Review dimension: {section_name}

{fenced_program}

{fenced_conventions}

CV:
{cv_context}
"""
        started = time.perf_counter()
        last_parse_error: Exception | None = None
        response = None
        raw = None
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt:
                attempt_prompt = (
                    "The previous response contained no valid JSON text. Return the "
                    "requested JSON object immediately, without reasoning.\n\n" + prompt
                )
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=REVIEW_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": attempt_prompt}],
            )
            try:
                raw = RawCVSection.model_validate_json(
                    _json_object(_response_text(response))
                )
                break
            except ValueError as exc:
                last_parse_error = exc
                logger.warning(
                    "CV review section returned invalid content",
                    extra={
                        "section": section_name,
                        "attempt": attempt + 1,
                        "stop_reason": getattr(response, "stop_reason", None),
                        "content_types": [
                            getattr(block, "type", type(block).__name__)
                            for block in getattr(response, "content", [])
                        ],
                    },
                )
        if raw is None or response is None:
            raise ValueError(
                f"CV review returned no valid JSON for {section_name}"
            ) from last_parse_error

        latency_ms = (time.perf_counter() - started) * 1000
        result = CVReviewSection(
            name=raw.name,
            score=raw.score,
            issues=raw.issues,
            suggestions=raw.suggestions,
        )
        usage = getattr(response, "usage", None)
        return CVSectionExecution(
            result=result,
            prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            latency_ms=latency_ms,
        )

    async def review_all_sections(
        self,
        *,
        cv_context: str,
        target_country: str,
        target_field: str,
        country_conventions: str,
        program_context: dict[str, Any] | None = None,
    ) -> CVReviewExecution:
        """Review every dimension in one bounded model request.

        The old implementation submitted five large prompts concurrently. On
        the live AgentRouter that exhausted output budgets and then saturated
        the model queue. A single structured response is faster, cheaper, and
        has one deadline the API can actually enforce.
        """
        system = (
            "You are the GOA CV Review Agent. Compare the supplied CV with the "
            "selected study programme and return only the requested JSON. Do "
            "not include reasoning, thinking, markdown, or commentary. Start "
            "immediately with the JSON object."
        )
        fenced_conventions = wrap_untrusted(
            country_conventions[:4000],
            label="COUNTRY CONVENTION CONTEXT",
            origin="trusted application guidance about the target country",
        )
        fenced_program = wrap_untrusted(
            json.dumps(program_context or {}, ensure_ascii=False, indent=2)[:6000],
            label="SELECTED PROGRAMME REQUIREMENTS",
            origin="the programme catalogue owned by the RAG service",
        )
        section_list = json.dumps(list(SECTION_NAMES), ensure_ascii=False)
        prompt = f"""Return one JSON object with this exact shape:
{{
  "sections": [
    {{
      "name": "one exact name from the required list",
      "score": 0,
      "issues": ["specific problem found"],
      "suggestions": ["specific action the candidate can take"]
    }}
  ]
}}

Required section names, in this exact order: {section_list}

Rules:
- Return exactly five sections, once each, in the required order.
- Each score is an integer from 0 to 100.
- Use at most three concise issues and three concise suggestions per section.
- Judge only the supplied CV; never invent credentials or programme requirements.
- If a skills section is absent, say so explicitly under Skills gaps.
- Make every suggestion a concrete content, rewrite, formatting, or evidence action.
- Treat programme requirements as authoritative. Treat country conventions as
  guidance, not admissions requirements, and state uncertainty where relevant.

Target country: {target_country}
Target field or programme: {target_field}

{fenced_program}

{fenced_conventions}

CV:
{cv_context}
"""
        started = time.perf_counter()
        last_parse_error: Exception | None = None
        response = None
        parsed = None
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt:
                attempt_prompt = (
                    "The previous response did not contain the required valid JSON. "
                    "Return the complete five-section JSON object now.\n\n" + prompt
                )
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=REVIEW_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": attempt_prompt}],
            )
            try:
                candidate = RawCVReview.model_validate_json(
                    _json_object(_response_text(response))
                )
                by_name = {item.name.casefold(): item for item in candidate.sections}
                missing = [
                    name for name in SECTION_NAMES if name.casefold() not in by_name
                ]
                if missing or len(by_name) != len(SECTION_NAMES):
                    raise ValueError(f"missing or duplicate review sections: {missing}")
                parsed = candidate
                break
            except ValueError as exc:
                last_parse_error = exc
                logger.warning(
                    "CV review returned invalid aggregate content",
                    extra={
                        "attempt": attempt + 1,
                        "stop_reason": getattr(response, "stop_reason", None),
                        "content_types": [
                            getattr(block, "type", type(block).__name__)
                            for block in getattr(response, "content", [])
                        ],
                    },
                )
        if parsed is None or response is None:
            raise ValueError("CV review returned no valid five-section JSON") from last_parse_error

        by_name = {item.name.casefold(): item for item in parsed.sections}
        sections = [
            CVReviewSection(
                name=by_name[name.casefold()].name,
                score=by_name[name.casefold()].score,
                issues=by_name[name.casefold()].issues,
                suggestions=by_name[name.casefold()].suggestions,
            )
            for name in SECTION_NAMES
        ]
        usage = getattr(response, "usage", None)
        return CVReviewExecution(
            sections=sections,
            prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class CVReviewCoordinator:
    def __init__(self, runner: CVReviewRunner) -> None:
        self.runner = runner

    async def review(
        self,
        *,
        extracted_text: str | None,
        structured_data: dict[str, Any] | None,
        target_country: str,
        target_field: str,
        country_conventions: str,
        program_context: dict[str, Any] | None = None,
        on_partial: PartialCallback | None = None,
    ) -> CVReviewSummary:
        cv_context = _build_cv_context(extracted_text, structured_data)

        execution = await asyncio.wait_for(
            self.runner.review_all_sections(
                cv_context=cv_context,
                target_country=target_country,
                target_field=target_field,
                country_conventions=country_conventions,
                program_context=program_context,
            ),
            timeout=REVIEW_REQUEST_TIMEOUT_SECONDS,
        )
        sections = execution.sections
        for section in sections:
            await _notify(on_partial, section)
        overall_score = round(sum(item.score for item in sections) / len(sections))
        return CVReviewSummary(
            overall_score=overall_score,
            sections=sections,
            total_tokens=execution.prompt_tokens + execution.completion_tokens,
        )

    async def replay_cached(
        self,
        payload: dict[str, Any],
        *,
        on_partial: PartialCallback | None = None,
    ) -> CVReviewSummary:
        response = CVReviewResponse.model_validate(payload)
        for section in response.sections:
            await _notify(on_partial, section)
        return CVReviewSummary(
            overall_score=response.overallScore,
            sections=response.sections,
            total_tokens=0,
        )


def get_redis_client(settings: Settings):
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


async def get_cached_review(cache_client: Any, cache_key: str) -> dict[str, Any] | None:
    cached = await maybe_await(cache_client.get(cache_key))
    if not cached:
        return None
    return json.loads(cached)


async def set_cached_review(cache_client: Any, cache_key: str, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, separators=(",", ":"))
    await maybe_await(cache_client.setex(cache_key, CACHE_TTL_SECONDS, serialized))


def cv_review_response(summary: CVReviewSummary) -> CVReviewResponse:
    return CVReviewResponse(overallScore=summary.overall_score, sections=summary.sections)


@lru_cache
def get_cv_review_coordinator() -> CVReviewCoordinator:
    from anthropic import AsyncAnthropic

    settings = get_settings()
    key = settings.anthropic_api_key or "not-configured"
    client = AsyncAnthropic(
        api_key=key,
        timeout=REVIEW_TIMEOUT_SECONDS,
        max_retries=1,
        default_headers={"User-Agent": settings.anthropic_user_agent},
        **({"base_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    )
    return CVReviewCoordinator(CVReviewRunner(client, model=settings.cv_review_model))
