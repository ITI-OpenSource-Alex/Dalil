"""Supervise discovered visa sources before they reach a student (SPEAK/visa).

Discovery finds official pages. It is not reliable about finding the *right*
official page: on a four-country trial it returned one clean result, one miss,
one news article about an agency starting operations, and one route addressed to
Emirati applicants. The allowlist keeps unofficial pages out; it cannot tell a
requirements page from a press release.

That gap is a judgement, so it gets a judge. With one rule.

**The supervisor may only REJECT or FLAG. It can never promote.**

It runs after the deterministic filters and can only narrow what survives. If a
model could rescue a candidate the allowlist rejected, the allowlist would stop
being a guarantee -- and it is the only thing currently keeping consultancy blogs
and other nationalities' routes away from a student. So the worst this component
can do is lower recall, which is visible and safe. It can never widen what the
system treats as authoritative, which would be neither.

**Its purpose is to shrink human review, not replace it.**

Every source still ends up in one of three states. ACCEPT means the cheap
deterministic checks and the model agree, and the source is usable. REVIEW means
something is uncertain and a person should look. REJECT means it is disqualified.
The value is that a reviewer reads the REVIEW pile instead of all thirty.

**Deterministic checks run first and can decide alone.**

They are free, they cannot hallucinate, and they catch the failures that matter
most -- a page that never mentions Egypt cannot be the Egyptian route. The model
is asked only about what they cannot settle: is this the requirements page, or
something adjacent to it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class Verdict(str, Enum):
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


@dataclass
class Supervision:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    #: Only ever set by the model, and only consulted for ordering the review
    #: pile. It never decides a verdict on its own.
    model_confidence: float | None = None
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """ACCEPT alone. REVIEW is not a soft accept."""
        return self.verdict is Verdict.ACCEPT


# Wording that marks a page as describing requirements rather than mentioning
# them. Deliberately broad: this decides whether to ASK the model, not whether
# to trust the page.
REQUIREMENT_MARKERS = (
    "requirement", "documents required", "checklist", "how to apply",
    "supporting documents", "financial", "means of subsistence",
    "proof of funds", "blocked account", "sufficient funds",
    "application process", "eligibility",
)

# Wording that marks a page as adjacent to the topic rather than about it. The
# Portugal trial returned a news item announcing an agency's launch: correct
# domain, correct authority, no requirements on it at all.
NON_REQUIREMENT_MARKERS = (
    "press release", "news", "newsroom", "communiqu", "noticias", "notícias",
    "press office", "annual report", "vacancy", "tender", "job opening",
)

# The applicant this catalogue serves. A page with no mention of Egypt may still
# be a generic national requirements page, which is legitimate -- but a page
# naming a different nationality is not.
APPLICANT_TOKENS = ("egypt", "egyptian", "cairo")

# Words in an authority's name that carry no identifying power. Without this,
# "and" or "the" matches any page and the issuing-body check passes for free.
_BODY_STOPWORDS = frozenset({
    "and", "the", "for", "of", "office", "service", "services", "agency",
    "ministry", "department", "national", "general", "affairs", "board",
    "directorate", "bureau", "authority", "inspectorate",
})
OTHER_NATIONALITY_TOKENS = (
    "emirati", "united arab emirates", "indian nationals", "pakistani nationals",
    "nigerian nationals", "chinese nationals", "turkish nationals",
    "saudi nationals", "filipino nationals",
)


def deterministic_checks(
    *, url: str, page_text: str, country: str, issuing_body: str
) -> tuple[list[str], list[str]]:
    """Free checks over the fetched page. Returns (passed, failed).

    These run before the model and can disqualify a source on their own. They
    cannot hallucinate, and they catch the failure that matters most: a page
    addressed to somebody else.
    """
    text = (page_text or "").lower()
    passed: list[str] = []
    failed: list[str] = []

    if len(text) < 400:
        failed.append("page_too_short: under 400 characters of text to assess")
    else:
        passed.append("page_has_content")

    if any(token in text for token in REQUIREMENT_MARKERS):
        passed.append("mentions_requirements")
    else:
        failed.append("no_requirement_language: nothing resembling a document or funds requirement")

    # A press release on the right domain is the Portugal case.
    if any(token in text[:1500] for token in NON_REQUIREMENT_MARKERS):
        failed.append("reads_as_news: the opening looks like an announcement, not a requirements page")

    # The decisive one. A page naming a different nationality's route is
    # authoritative, well-formed and about the wrong person.
    if any(token in text for token in OTHER_NATIONALITY_TOKENS):
        failed.append("addresses_another_nationality")
    elif any(token in text for token in APPLICANT_TOKENS):
        passed.append("names_egyptian_applicants")
    else:
        # Not a failure. Plenty of national portals describe one process for all
        # third-country nationals, and that process is the Egyptian one too.
        passed.append("generic_national_page")

    # len >= 3, not > 3. The stricter bound silently discarded every short
    # acronym -- IND, UDI, SEM, IGI are all real authorities in visa_sources --
    # so those countries could never pass this check no matter what page they
    # were given. Stopwords are removed separately, because "and" and "for"
    # appear on every page and would pass it for free.
    body_terms = {
        t for t in re.split(r"\W+", issuing_body.lower())
        if len(t) >= 3 and t not in _BODY_STOPWORDS
    }
    if not body_terms:
        # Nothing distinctive to look for. Inconclusive, not absent: recording a
        # failure here would penalise a source for the shape of its own name.
        passed.append("issuing_body_not_checkable")
    elif any(term in text or term in url.lower() for term in body_terms):
        passed.append("names_issuing_body")
    else:
        failed.append("issuing_body_absent: the named authority does not appear")

    if country.lower() in text:
        passed.append("names_destination_country")

    return passed, failed


SUPERVISOR_PROMPT = """You are checking whether a web page is the official \
student-visa requirements page that a specific authority publishes for \
EGYPTIAN applicants.

You are a filter, not a researcher. You cannot approve anything the caller has \
not already established is on an official domain. Judge only what is in front \
of you.

Answer with a single JSON object and nothing else:

{"is_requirements_page": true|false,
 "serves_egyptian_applicants": true|false|null,
 "mentions_financial_requirement": true|false,
 "financial_amount_present": true|false,
 "confidence": 0.0-1.0,
 "reason": "one sentence"}

Rules:
- "is_requirements_page" is false for news, press releases, agency landing \
pages, and general information pages that do not state what an applicant must \
provide.
- "serves_egyptian_applicants" is null when the page describes one process for \
all non-EU applicants without naming nationalities. That is legitimate. It is \
false only when the page is clearly addressed to a different nationality.
- Do not infer a financial amount that is not written on the page. An absent \
figure is more useful than a guessed one.
- If you are unsure, say so with a low confidence rather than choosing."""


async def ask_model(
    anthropic, model: str, *, url: str, page_text: str, country: str, issuing_body: str
) -> dict | None:
    """One supervision call. Returns the parsed judgement, or None if it failed.

    None means "the model could not help", which routes to REVIEW. It never
    routes to ACCEPT: an unavailable supervisor must not silently approve.
    """
    try:
        response = await anthropic.messages.create(
            model=model,
            # Sized for thinking plus a small JSON object. The extraction path
            # in this service was starved at 4000 by a thinking block and
            # reported it as unparseable JSON; no reason to repeat that here.
            max_tokens=2048,
            system=SUPERVISOR_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"Authority: {issuing_body}\nDestination country: {country}\n"
                    f"URL: {url}\n\nPAGE TEXT:\n{page_text[:12000]}"
                ),
            }],
        )
    except Exception as error:
        logger.warning("visa_supervisor_call_failed", url=url, error=str(error))
        return None

    if getattr(response, "stop_reason", None) == "max_tokens":
        logger.warning("visa_supervisor_truncated", url=url)
        return None

    text = ""
    for block in response.content:
        candidate = getattr(block, "text", "")
        if candidate and "{" in candidate:
            text = candidate
            break
    if not text:
        return None

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("visa_supervisor_unparseable", url=url, text=text[:200])
        return None


async def supervise(
    anthropic,
    model: str,
    *,
    url: str,
    page_text: str,
    country: str,
    issuing_body: str,
    review_below_confidence: float = 0.75,
) -> Supervision:
    """Decide whether a discovered source may be used.

    Order matters: deterministic checks first, and a hard failure ends it
    without spending a model call. The model is only asked about what the cheap
    checks cannot settle.
    """
    passed, failed = deterministic_checks(
        url=url, page_text=page_text, country=country, issuing_body=issuing_body
    )

    # Disqualifying on their own. A page addressed to another nationality is the
    # one failure that produces a confident wrong answer for a student, so it
    # never reaches the model and never reaches review -- there is nothing to
    # discuss.
    hard = [f for f in failed if f.startswith(("addresses_another_nationality", "page_too_short"))]
    if hard:
        return Supervision(
            verdict=Verdict.REJECT, reasons=hard,
            checks_passed=passed, checks_failed=failed,
        )

    judgement = await ask_model(
        anthropic, model, url=url, page_text=page_text,
        country=country, issuing_body=issuing_body,
    )

    if judgement is None:
        # An unavailable supervisor routes to review, never to accept. A source
        # nobody could check is not a checked source.
        return Supervision(
            verdict=Verdict.REVIEW,
            reasons=["supervisor_unavailable: the check could not be completed"],
            checks_passed=passed, checks_failed=failed,
        )

    reasons: list[str] = []
    if judgement.get("reason"):
        reasons.append(str(judgement["reason"]))

    if judgement.get("serves_egyptian_applicants") is False:
        return Supervision(
            verdict=Verdict.REJECT,
            reasons=reasons + ["model: page serves a different nationality"],
            model_confidence=judgement.get("confidence"),
            checks_passed=passed, checks_failed=failed,
        )

    if not judgement.get("is_requirements_page"):
        return Supervision(
            verdict=Verdict.REJECT,
            reasons=reasons + ["model: not a requirements page"],
            model_confidence=judgement.get("confidence"),
            checks_passed=passed, checks_failed=failed,
        )

    confidence = judgement.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0

    # Everything below is a REVIEW rather than a REJECT: the source looks right
    # and something is merely unconfirmed. This is the pile a person reads.
    if confidence < review_below_confidence:
        reasons.append(f"model confidence {confidence:.2f} below {review_below_confidence:.2f}")
        return Supervision(
            verdict=Verdict.REVIEW, reasons=reasons, model_confidence=confidence,
            checks_passed=passed, checks_failed=failed,
        )

    if failed:
        reasons.append("deterministic checks raised: " + "; ".join(failed))
        return Supervision(
            verdict=Verdict.REVIEW, reasons=reasons, model_confidence=confidence,
            checks_passed=passed, checks_failed=failed,
        )

    if not judgement.get("mentions_financial_requirement"):
        # Not disqualifying -- some authorities split funds onto a second page --
        # but a student's checklist depends on it, so a human decides.
        reasons.append("no financial requirement found on this page")
        return Supervision(
            verdict=Verdict.REVIEW, reasons=reasons, model_confidence=confidence,
            checks_passed=passed, checks_failed=failed,
        )

    return Supervision(
        verdict=Verdict.ACCEPT,
        reasons=reasons or ["all checks passed"],
        model_confidence=confidence,
        checks_passed=passed, checks_failed=failed,
    )
