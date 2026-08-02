"""PII detection and redaction (OWASP LLM06).

Redaction is lossy and both failure directions hurt:

  Too aggressive: "Your GPA of [redacted-phone] qualifies you" -- the product is
  broken, and the user cannot tell whether the system is confused or censoring.

  Too permissive: a real person's contact details flow into logs, Langfuse
  traces and a third-party model provider, none of which are covered by the
  deletion promise the product makes.

There is no correct setting, only a decision with tests pinning it. These
patterns are tuned toward *precision* -- fewer false positives -- because this
runs over answers users read. The gap that leaves is unstructured PII ("my
father Ahmed who lives near Tahrir"), which no regex can catch; that is what the
LLM check on the CV and essay paths is for.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class PIIPattern(NamedTuple):
    label: str
    regex: re.Pattern[str]


PII_PATTERNS: tuple[PIIPattern, ...] = (
    PIIPattern("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    # Egyptian national ID: exactly 14 digits. Checked before the phone pattern
    # so a national ID is labelled as one rather than as a long phone number.
    PIIPattern("national-id", re.compile(r"(?<![\d-])\d{14}(?![\d-])")),
    PIIPattern(
        "phone",
        # Egyptian local (01xxxxxxxxx) and international (+20 1xx xxx xxxx).
        # The leading zero is dropped in international format, so requiring it
        # would have missed every number written the way a student abroad writes
        # their own.
        #
        # The structure demands 10-11 digits in three groups, which is what
        # keeps it away from ordinary numbers: "11904 EUR in a blocked account"
        # and "129.40 per semester" must survive untouched, because
        # blocked-account amounts are the substance of a visa answer. The
        # lookarounds stop a partial match inside a longer digit run.
        re.compile(
            r"(?<![\d.])"
            r"(?:\+\d{1,3}[\s-]?)?"
            r"(?:0\d{2}|\d{3})"
            r"[\s-]?\d{3,4}[\s-]?\d{4}"
            r"(?![\d.])"
        ),
    ),
    PIIPattern("passport", re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")),
    PIIPattern(
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    ),
    PIIPattern(
        "card",
        # 13-19 digits in groups. Financial data has no business in an answer
        # about study abroad under any circumstances.
        re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?![\d-])"),
    ),
)


def redact_pii(value: str) -> tuple[str, list[str]]:
    """Replace PII spans with labelled markers.

    Returns the redacted text and the labels that fired, so the caller can count
    what happened without logging what was found.

    The marker is visible on purpose. Silently deleting a phone number produces
    a sentence that reads as though the model forgot something; "[redacted-phone]"
    tells the reader a decision was made on their behalf.
    """
    if not value:
        return value, []

    redacted = value
    found: list[str] = []
    for pattern in PII_PATTERNS:
        redacted, count = pattern.regex.subn(f"[redacted-{pattern.label}]", redacted)
        if count:
            found.append(pattern.label)
    return redacted, found


def has_pii(value: str) -> bool:
    """True when any PII pattern matches. Does not modify the text."""
    if not value:
        return False
    return any(pattern.regex.search(value) for pattern in PII_PATTERNS)
