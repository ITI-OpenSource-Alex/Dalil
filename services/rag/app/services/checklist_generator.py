import re
import time
from typing import Any

import structlog
from langchain_anthropic import ChatAnthropic

from app.core.config import settings
from app.core.metrics import CHECKLIST_GENERATED_TOTAL, CHECKLIST_GENERATION_LATENCY
from app.schemas.checklists import GeneratedChecklist, GeneratedChecklistItem
from app.schemas.scoring import ProgramRequirements

logger = structlog.get_logger("rag_service.checklist_generator")

MAX_ITEMS = 15

# Used verbatim when the LLM call fails or returns an empty/invalid checklist, so a
# user still gets something actionable rather than a 500 -- same graceful-degradation
# shape as llm_boost.py's boost_value=0 fallback.
_BASELINE_ITEMS = [
    GeneratedChecklistItem(
        item_id="valid_passport",
        title="Valid passport",
        description="Ensure your passport is valid for at least 6 months beyond your intended travel date.",
        category="documents",
    ),
    GeneratedChecklistItem(
        item_id="academic_transcripts",
        title="Academic transcripts",
        description="Obtain certified transcripts from all previously attended institutions.",
        category="documents",
    ),
    GeneratedChecklistItem(
        item_id="motivation_letter",
        title="Motivation letter",
        description="Write a statement of purpose explaining your interest in the program.",
        category="documents",
    ),
    GeneratedChecklistItem(
        item_id="recommendation_letters",
        title="Recommendation letters",
        description="Request at least two academic or professional reference letters.",
        category="documents",
    ),
    GeneratedChecklistItem(
        item_id="application_fee",
        title="Pay application fee",
        description="Check the program's application portal for the required fee and payment method.",
        category="administrative",
    ),
]


def _normalize_items(items: list[GeneratedChecklistItem]) -> list[dict[str, Any]]:
    """Slugify and de-duplicate LLM-authored item_ids.

    item_id becomes checklist_item_states.item_key permanently once persisted, so it
    must be unique within the checklist and safe to use as an opaque key -- never
    trust the LLM's own slug to already satisfy that.
    """
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in items[:MAX_ITEMS]:
        slug = re.sub(r"[^a-z0-9_]+", "_", item.item_id.strip().lower()).strip("_") or "item"
        candidate = slug
        suffix = 2
        while candidate in seen:
            candidate = f"{slug}_{suffix}"
            suffix += 1
        seen.add(candidate)
        normalized.append(
            {
                "item_id": candidate,
                "title": item.title.strip()[:255],
                "description": (item.description or "").strip()[:1000] or None,
                "category": (item.category or "").strip()[:100] or None,
            }
        )
    return normalized


def fallback_checklist() -> list[dict[str, Any]]:
    return _normalize_items(_BASELINE_ITEMS)


def _build_prompt(
    program: ProgramRequirements, profile: dict[str, Any] | None, gap_report: dict[str, Any]
) -> str:
    gap_lines = (
        "\n".join(f"- {key}: {value.get('message', value)}" for key, value in gap_report.items())
        or "None identified."
    )
    profile_lines = (
        f"Degree level: {profile.get('degreeLevel')}, GPA: {profile.get('gpa')}, "
        f"IELTS: {profile.get('ieltsScore')}, "
        f"Work experience: {profile.get('workExperienceYears')} years"
        if profile
        else "No profile on file."
    )
    return f"""You are an admissions assistant. Generate a personalized application checklist
for a student applying to this program. Return between 5 and {MAX_ITEMS} concrete, actionable
items covering documents, language requirements, financial proof, and any gaps below.

PROGRAM:
Country: {program.country}
Degree level: {program.degree_level}
Minimum GPA: {program.min_gpa}
Minimum IELTS: {program.min_ielts}
Minimum ECTS: {program.min_ects}

CANDIDATE PROFILE:
{profile_lines}

IDENTIFIED GAPS:
{gap_lines}
"""


async def generate_checklist(
    user_id: str,
    program: ProgramRequirements,
    profile: dict[str, Any] | None,
    gap_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Generate checklist items via the LLM, degrading to a fixed baseline on any
    failure (timeout, malformed output, empty output). Returns (items, generated_by)
    where generated_by is "llm" or "fallback" -- callers persist that flag so a
    degraded checklist is never silently passed off as a generated one.
    """
    start = time.time()
    try:
        llm = ChatAnthropic(
            model=settings.llm_model,
            anthropic_api_key=settings.anthropic_auth_token or settings.anthropic_api_key,
            **(
                {"anthropic_api_url": settings.anthropic_base_url}
                if settings.anthropic_base_url
                else {}
            ),
            model_kwargs={"extra_headers": {"User-Agent": settings.anthropic_user_agent}},
            temperature=0.0,
            # langchain_anthropic 0.1.13 has no `timeout`/`max_retries` field on
            # ChatAnthropic: unrecognised kwargs are forwarded to
            # AsyncMessages.create(), which rejects max_retries. The supported
            # field is default_request_timeout. (This note used to point at
            # rag_service.py, whose ChatAnthropic was deleted in GOA-135 as dead
            # code -- llm_boost.py carries the same constraint.)
            default_request_timeout=25.0,
        )
        structured_llm = llm.with_structured_output(GeneratedChecklist, include_raw=True)

        prompt = _build_prompt(program, profile, gap_report)
        result = await structured_llm.ainvoke(prompt)
        parsed: GeneratedChecklist | None = result["parsed"]
        if not parsed or not parsed.items:
            raise ValueError("LLM returned no checklist items")

        raw = result["raw"]
        token_usage = raw.response_metadata.get("usage", {})
        input_tokens = getattr(token_usage, "input_tokens", 0)
        output_tokens = getattr(token_usage, "output_tokens", 0)
        if not input_tokens and isinstance(token_usage, dict):
            input_tokens = token_usage.get("input_tokens", 0)
            output_tokens = token_usage.get("output_tokens", 0)
        try:
            from app.telemetry import record_llm_cost

            record_llm_cost(user_id, settings.llm_model, input_tokens, output_tokens)
        except ImportError:
            logger.warning("telemetry helper not found")

        items = _normalize_items(parsed.items)
        CHECKLIST_GENERATED_TOTAL.labels(source="llm").inc()
        return items, "llm"
    except Exception as exc:
        logger.warning("checklist_generation_failed_using_fallback", error=str(exc))
        CHECKLIST_GENERATED_TOTAL.labels(source="fallback").inc()
        return fallback_checklist(), "fallback"
    finally:
        CHECKLIST_GENERATION_LATENCY.observe((time.time() - start) * 1000)
