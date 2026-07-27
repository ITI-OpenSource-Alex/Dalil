"""LLM review of an already-extracted CV.

The CV pipeline ended at extraction. Since BUG-018 was fixed it reliably
produces good structured data -- name, degree, institution, skills, work
history -- and nothing consumed it. Orchestration's CV_REVIEW intent had no
endpoint to call, and POST /cv/review 404'd on both the writing service and the
gateway (BUG-019).

The client construction here mirrors agents.py deliberately, including all four
things BUG-018 had to fix: the gateway base_url, the pinned User-Agent, a model
the gateway actually serves, and no `temperature` (the gateway fronts Bedrock,
which rejects the parameter outright for this model).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents import _json_object, _response_text
from app.config import get_settings

logger = logging.getLogger(__name__)

REVIEW_MODEL = "claude-opus-4-8"

# Generous on purpose — see the client construction below for why 25s is not
# enough for this particular call.
REVIEW_TIMEOUT_SECONDS = 120.0

_PROMPT = """You are reviewing a CV for a student applying to study abroad, \
typically for a Master's programme in Europe.

Return ONLY a JSON object with this exact shape:

{
  "summary": "two or three sentences on the candidate's overall profile",
  "sections": [
    {
      "section": "Education" | "Experience" | "Skills" | "Structure" | "Other",
      "strengths": ["..."],
      "gaps": ["..."],
      "suggestions": ["concrete, actionable rewrite advice"]
    }
  ],
  "readiness": "strong" | "adequate" | "needs_work",
  "missing_for_study_abroad": ["items an admissions committee expects and this CV lacks"]
}

Rules:
- Judge only what the CV says. Do not invent experience, dates or institutions.
- If a section is genuinely absent from the CV, say so in gaps rather than \
inventing strengths for it.
- suggestions must be specific enough to act on. "Improve your summary" is \
useless; "state your thesis topic and supervisor" is not.
- readiness is about admissions readiness, not a grade.
"""


def _build_input(extracted_text: str | None, structured: dict[str, Any] | None) -> str:
    parts = []
    if structured:
        parts.append(
            "Structured data extracted from the CV:\n"
            + json.dumps(structured, indent=2, ensure_ascii=False)
        )
    if extracted_text:
        # Truncated because a CV is short and the tail of a long PDF is usually
        # references or boilerplate. Sending an unbounded document to the model
        # would make cost a function of whatever the user uploaded.
        parts.append("Raw CV text:\n" + extracted_text[:20000])
    return "\n\n".join(parts)


async def review_cv(
    extracted_text: str | None,
    structured_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the parsed review object, or raise for the caller to translate."""
    from anthropic import AsyncAnthropic

    settings = get_settings()
    key = settings.anthropic_api_key
    if not key or key == "not-configured":
        logger.warning("ANTHROPIC_API_KEY is not configured; CV review will fail")
        key = "not-configured"

    # Not settings.anthropic_timeout_seconds (25s).
    #
    # That default is tuned for the short criterion calls in agents.py. A CV
    # review is a single ~2000-token structured generation against a gateway
    # measured between 2.5s and 110s, so 25s does not fit it. The first run of
    # this endpoint failed at exactly 78.3s: 25s x 3 attempts, the SDK's two
    # retries included, reported as APITimeoutError.
    #
    # max_retries is dropped to 1 so the worst case stays inside the gateway's
    # 5-minute client rather than turning one slow call into a four-minute wait.
    client = AsyncAnthropic(
        api_key=key,
        timeout=REVIEW_TIMEOUT_SECONDS,
        max_retries=1,
        default_headers={"User-Agent": settings.anthropic_user_agent},
        **({"base_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    )

    response = await client.messages.create(
        model=REVIEW_MODEL,
        # No `temperature`: the gateway fronts Bedrock, which rejects it for
        # this model. GOA-028 removed it from agents.py for the same reason and
        # BUG-018 hit it again in the CV processor.
        max_tokens=2000,
        system=_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _build_input(extracted_text, structured_data),
            }
        ],
    )

    return json.loads(_json_object(_response_text(response)))
