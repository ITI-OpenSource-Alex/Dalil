"""Shared structured-extraction helpers for scholarship adapters.

Lifted out of daad.py unchanged (BUG-010b) so the single-programme adapters --
Chevening and Stipendium Hungaricum -- can emit scholarship_programs records
without duplicating regexes that were already tuned against real live pages.

The governing rule is the one DAAD's extractor was built on: a field the page
does not state unambiguously stays None. A guessed deadline or an assumed IELTS
minimum is worse than a null, because GOA-024's matcher treats what it reads
here as fact.
"""
import re
from datetime import datetime

DEADLINE_LABELS = {"application deadline", "deadline"}
VALUE_LABELS = {"scholarship value", "value", "funding", "amount"}
ELIGIBILITY_LABELS = {"who can apply?", "who can apply", "target group", "eligibility"}
ALL_SECTION_LABELS = DEADLINE_LABELS | VALUE_LABELS | ELIGIBILITY_LABELS | {
    "duration", "benefits", "about the daad scholarship", "selection criteria",
    "overview", "objective", "what can be funded?", "duration of the funding",
    "selection", "application requirements", "what requirements must be met?",
    "language skills", "application procedure", "application documents",
}

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTHS})\s+(\d{{4}})\b", re.IGNORECASE)

# EUR-only, matching either currency ordering. DAAD keeps using this one so its
# behaviour is provably unchanged by the refactor.
AMOUNT_EUR_RE = re.compile(
    r"(?:€|EUR|euros?)\s?[\d][\d.,]*|[\d][\d.,]*\s?(?:€|EUR|euros?)\b",
    re.IGNORECASE,
)

# Multi-currency, for the UK (GBP) and Hungarian (HUF/Ft) sources.
AMOUNT_RE = re.compile(
    r"(?:€|£|EUR|GBP|HUF|Ft|euros?|pounds?|forints?)\s?[\d][\d.,]*"
    r"|[\d][\d.,]*\s?(?:€|£|EUR|GBP|HUF|Ft|euros?|pounds?|forints?)\b",
    re.IGNORECASE,
)

DEGREE_LEVEL_PATTERNS = [
    (re.compile(r"\bresearch\s+grants?\b", re.IGNORECASE), "Research Grant"),
    (re.compile(r"\bdoctoral\b|\bphd\b|\bph\.d\.\b", re.IGNORECASE), "PhD"),
    (re.compile(r"\bmaster'?s?\b", re.IGNORECASE), "Master"),
    (re.compile(r"\bbachelor'?s?\b", re.IGNORECASE), "Bachelor"),
]

IELTS_RE = re.compile(r"IELTS[^\d]{0,40}(\d(?:\.\d)?)", re.IGNORECASE)
GPA_RE = re.compile(r"GPA[^\d]{0,60}(\d\.\d{1,2})", re.IGNORECASE)


def lines_from(text_content: str) -> list[str]:
    return [line.strip() for line in text_content.split("\n") if line.strip()]


def section_text_after_label(lines: list[str], label_variants: set[str], max_lines: int = 12) -> str | None:
    """Finds a standalone line matching one of label_variants and collects the
    following lines as that section's raw text, stopping at the next recognized
    section label (or max_lines) rather than a fixed window -- avoids bleeding into
    a neighboring section's content. Returns None if the label itself isn't found
    or its section has no content."""
    for i, line in enumerate(lines):
        if line.lower() not in label_variants:
            continue
        collected = []
        for candidate in lines[i + 1: i + 1 + max_lines]:
            if candidate.lower() in ALL_SECTION_LABELS:
                break
            collected.append(candidate)
        if collected:
            return "\n".join(collected)
    return None


def extract_deadline(section_text: str | None):
    if not section_text:
        return None
    match = DATE_RE.search(section_text)
    if not match:
        return None
    day, month_name, year = match.group(1), match.group(2), match.group(3)
    try:
        return datetime.strptime(f"{day} {month_name.capitalize()} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def extract_award_amount(section_text: str | None, pattern: re.Pattern = AMOUNT_EUR_RE) -> str | None:
    if not section_text or not pattern.search(section_text):
        return None
    return section_text[:255]


def extract_eligibility(section_text: str | None) -> dict:
    if not section_text:
        return {}
    items = [line for line in section_text.split("\n") if line.strip()]
    return {"items": items} if items else {}


def extract_degree_level(
    text_content: str, name: str | None = None, none_if_ambiguous: bool = False
) -> str | None:
    """Checks the scholarship name/title first, since it reliably states the
    degree actually being AWARDED (e.g. "Study Scholarships - Master Studies for
    All Academic Disciplines"). The whole-body-text fallback below is a real
    false-positive risk on live pages: confirmed against a real live DAAD
    scholarship, where the eligibility section states a PREREQUISITE degree
    ("you must have completed... Bachelor's or Diplom") earlier in the page than
    the funding description states the degree actually offered -- a naive
    earliest-occurrence scan over the full text incorrectly returned "Bachelor"
    for a scholarship titled "...Master Studies...". Title-first resolves that
    without discarding the fallback for scholarships whose title doesn't state a
    degree word at all.

    none_if_ambiguous is for programmes that genuinely span several levels at
    once (Stipendium Hungaricum funds bachelor's, master's AND doctoral study
    under one call). Earliest-occurrence would label that whole programme
    "Bachelor", which is not a truth about it -- None is.
    """
    if name:
        for pattern, label in DEGREE_LEVEL_PATTERNS:
            if pattern.search(name):
                return label

    matches = [
        (match, label)
        for match, label in (
            (pattern.search(text_content), label) for pattern, label in DEGREE_LEVEL_PATTERNS
        )
        if match is not None
    ]
    if not matches:
        return None
    if none_if_ambiguous and len({label for _, label in matches}) > 1:
        return None
    return min(matches, key=lambda pair: pair[0].start())[1]


def extract_numeric_field(text_content: str, pattern: re.Pattern) -> float | None:
    match = pattern.search(text_content)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None
