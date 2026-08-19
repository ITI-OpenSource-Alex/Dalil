"""GOA-045 -- which questions are allowed to be answered from the curated FAQ.

The FAQ short-circuit is valuable precisely because it is cheap: a hit skips
embedding, retrieval and the LLM entirely. That same property is what makes it
dangerous. A cached answer is a snapshot of what was true when somebody wrote
it, so the moment a question's answer depends on a number that an authority can
change -- a blocked-account minimum, a visa fee, an application deadline, an
eligibility threshold -- serving it from static text is worse than being slow.
It is confidently wrong, with no citation the user can check.

So the rule is not "prefer fresh data when convenient". It is: a question whose
answer is source-sensitive must NEVER be served by the FAQ, even when it fuzzy
matches a curated entry with high similarity. That is what this module decides.

Two independent controls, deliberately:

1.  Curation. Entries in `faq_entries` are supposed to be stable procedural
    explanations only ("what is a Studienkolleg", "how do I book a VFS
    appointment"). Migration 028 removed the ones that were not.
2.  This classifier, applied to the *question* before matching.

Control 1 alone is not enough, and the reason is specific to fuzzy matching.
pg_trgm compares character trigrams, so "How much money do I need in my blocked
account?" and "How do I open a blocked account?" are lexically close while
having completely different answers -- one is a number that changes yearly, the
other is a procedure that does not. A perfectly curated FAQ can still be reached
by a volatile question through similarity alone. This module is what stops that.

Erring toward retrieval is the cheap mistake. A false positive here costs one
LLM call; a false negative quotes a stale legal or financial figure to someone
making an immigration decision on it.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Each pattern carries the reason it exists, so a future reader can tell a
# deliberate rule from an accidental one -- and so the bypass metric can say
# WHICH class of volatility fired rather than just "something did".
#
# Patterns are matched case-insensitively against the raw question.
_VOLATILE_PATTERNS: list[tuple[str, str]] = [
    # --- Monetary amounts -------------------------------------------------
    # Blocked-account minimums and visa fees are set by authorities and revised
    # on their own schedule; the Sperrkonto figure has moved several times.
    (
        "amount",
        r"\bhow much\b"
        r"|\bhow many euros?\b"
        r"|\bwhat (?:is|are) the (?:cost|costs|fee|fees|price|amount)\b"
        r"|\b(?:cost|fee|price)s? (?:of|for)\b"
        r"|\b\d[\d,.]*\s*(?:eur|euros?|egp|usd|dollars?|pounds?)\b"
        r"|[€$£]\s*\d",
    ),
    # --- Proof of funds ---------------------------------------------------
    # Distinct from a bare amount: "is a parent sponsorship accepted instead of
    # a blocked account" is a rule, not a procedure, and rules change.
    (
        "proof_of_funds",
        r"\bproof of (?:funds|financial)\b"
        r"|\bfinancial (?:requirement|proof|means|capacity)\b"
        r"|\bblocked account (?:minimum|amount|balance|requirement)\b"
        r"|\bsperrkonto (?:minimum|amount|balance|requirement)\b"
        r"|\bhow much .*\b(?:blocked account|sperrkonto)\b"
        r"|\b(?:sponsor|sponsorship|scholarship) .*\b(?:instead of|in place of)\b",
    ),
    # --- Deadlines --------------------------------------------------------
    # Intake dates and application windows move every cycle.
    (
        "deadline",
        r"\bdeadlines?\b"
        r"|\bcut[- ]?off (?:date|time)\b"
        r"|\bclosing date\b"
        r"|\blast (?:date|day) to\b"
        r"|\bwhen (?:is|are) the .*\b(?:deadline|intake|semester start)\b"
        r"|\bapplication (?:window|period)\b",
    ),
    # --- Eligibility thresholds -------------------------------------------
    # "Do I qualify" always depends on the current rule, never on prose written
    # six months ago. Note this deliberately does NOT catch "what documents are
    # required", which is procedure -- see the negative cases in the tests.
    (
        "eligibility",
        r"\bam i eligible\b"
        r"|\bdo i qualify\b"
        r"|\beligibility (?:criteria|requirement|rule)\b"
        r"|\bminimum (?:score|grade|gpa|ielts|toefl|band|age)\b"
        r"|\b(?:age|gpa|ielts|toefl) (?:limit|requirement|threshold)\b"
        r"|\bis .*\b(?:ielts|toefl|gpa)\b.*\b(?:enough|sufficient|accepted)\b"
        r"|\bmaximum age\b",
    ),
    # --- Processing times -------------------------------------------------
    # Consulate and APS backlogs swing seasonally; a cached "4 to 8 weeks" is
    # the kind of answer someone plans a flight around.
    (
        "processing_time",
        r"\bhow long does .*\b(?:take|processing)\b"
        r"|\bprocessing time\b"
        r"|\bwaiting (?:time|period)\b"
        r"|\bhow many (?:days|weeks|months) .*\b(?:take|wait)\b",
    ),
]

_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (reason, re.compile(pattern, re.IGNORECASE)) for reason, pattern in _VOLATILE_PATTERNS
]


class FAQEligibility(NamedTuple):
    """Whether a question may be served from the curated FAQ, and why not."""

    allowed: bool
    reason: str | None  # the volatility class that blocked it, else None


def classify_question(question: str) -> FAQEligibility:
    """Reports whether `question` may be answered from the static FAQ.

    Returns the FIRST matching volatility class rather than all of them: the
    metric wants a single label per bypass, and the classes are listed in
    roughly descending order of how badly a stale answer would mislead.
    """
    if not question or not question.strip():
        return FAQEligibility(allowed=True, reason=None)

    for reason, pattern in _COMPILED:
        if pattern.search(question):
            return FAQEligibility(allowed=False, reason=reason)

    return FAQEligibility(allowed=True, reason=None)


def is_source_sensitive(question: str) -> bool:
    """Convenience wrapper for callers that only need the boolean."""
    return not classify_question(question).allowed
