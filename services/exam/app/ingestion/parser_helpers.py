"""
app/ingestion/parser_helpers.py
--------------------------------
Stateless utility functions for resolving OCR ambiguities that require
document-structure context. The parser calls these helpers when it has
identified the structural context (e.g., inside a Questions header).

These are NOT part of the normalizer. They return structured metadata
and let the parser make the final semantic decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "QuestionRangeParse",
    "PassageHeader",
    "TestMarker",
    "parse_question_range",
    "parse_passage_header",
    "classify_test_marker",
]


@dataclass(slots=True)
class QuestionRangeParse:
    """Result of attempting to parse a merged question range."""

    candidates: list[tuple[int, int]]
    ambiguous: bool


@dataclass(slots=True)
class PassageHeader:
    """Result of parsing a passage header with a potentially corrupted number."""

    raw_number: int
    candidates: list[int]


@dataclass(slots=True)
class TestMarker:
    """Classified test marker from a single line."""

    test_number: int
    is_toc: bool
    is_phantom: bool


# Unified regex for identifying question block headers (e.g. "Questions 1-5" or merged "Questions 1310")
QUESTION_BLOCK_RE = re.compile(
    r"(?i)\bQuestions?\s+(\d{1,2}\s*(?:-|to|and|)\s*\d{1,2}|\d{3,5})\b"
)

_PASSAGE_HEADER_RE = re.compile(
    r"^\s*READING\s+PASSAGE\s+(\d+)", re.IGNORECASE
)
_TEST_MARKER_RE = re.compile(r"^\s*Test\s+(\d+)\s*(.*?)\s*$", re.IGNORECASE)


def parse_question_range(raw: str) -> QuestionRangeParse | None:
    """Parse a potentially merged numeric range string.

    Given a raw number string (e.g., '1428'), attempt to find valid splits
    into (start, end) where start < end and both are positive integers.

    Returns None if the string is not a plausible merged range (e.g., single
    digit, or not purely numeric).

    Examples:
        '1428' -> candidates=[(14, 28)], ambiguous=False
        '123'  -> candidates=[(1, 23)], ambiguous=False  (12,3 invalid: 12>3)
        '1234' -> candidates=[(1, 234), (12, 34)], ambiguous=True
    """
    raw = raw.strip()
    if not raw.isdigit():
        return None
    if len(raw) < 3 or len(raw) > 5:
        return None

    candidates: list[tuple[int, int]] = []

    # 1. Standard splits (e.g. '1315' -> 13, 15)
    for split_pos in range(1, len(raw)):
        left = int(raw[:split_pos])
        right = int(raw[split_pos:])
        if left > 0 and right > 0 and left < right:
            candidates.append((left, right))

    # 2. OCR noise drop: Try omitting one middle digit (e.g. '1310' -> dash became '3' -> 1, 10)
    for drop_pos in range(1, len(raw) - 1):
        noisy_raw = raw[:drop_pos] + raw[drop_pos + 1 :]
        for split_pos in range(1, len(noisy_raw)):
            left = int(noisy_raw[:split_pos])
            right = int(noisy_raw[split_pos:])
            if left > 0 and right > 0 and left < right:
                candidates.append((left, right))

    if not candidates:
        return None

    return QuestionRangeParse(
        candidates=candidates,
        ambiguous=len(candidates) > 1,
    )


def parse_passage_header(line: str) -> PassageHeader | None:
    """Parse a potential READING PASSAGE header line.

    Extracts the raw number and provides all individual digits as candidates.
    Does NOT apply any validity filtering — the parser decides which
    candidate is correct based on structural context.

    Returns None if the line is not a passage header.

    Examples:
        'READING PASSAGE 74' -> raw_number=74, candidates=[7, 4]
        'READING PASSAGE 2'  -> raw_number=2, candidates=[2]
        'READING PASSAGE 13' -> raw_number=13, candidates=[1, 3]
        'READING PASSAGE 111' -> raw_number=111, candidates=[1]
    """
    m = _PASSAGE_HEADER_RE.match(line)
    if not m:
        return None

    raw_number = int(m.group(1))
    digits = str(raw_number)

    seen: set[int] = set()
    candidates: list[int] = []
    for d in digits:
        n = int(d)
        if n > 0 and n not in seen:
            seen.add(n)
            candidates.append(n)

    return PassageHeader(raw_number=raw_number, candidates=candidates)


def classify_test_marker(line: str) -> TestMarker | None:
    """Classify a single line as a potential test marker.

    Returns None if the line does not match a test marker pattern.
    Otherwise returns structured metadata about the marker.

    Examples:
        'Test 1'    -> TestMarker(1, is_toc=False, is_phantom=False)
        'Test 1 10' -> TestMarker(1, is_toc=True, is_phantom=False)
        'Test 7'    -> TestMarker(7, is_toc=False, is_phantom=True)
    """
    m = _TEST_MARKER_RE.match(line)
    if not m:
        return None

    test_number = int(m.group(1))
    trailing = m.group(2).strip()

    is_toc = bool(re.fullmatch(r"\d+", trailing)) if trailing else False
    is_phantom = test_number > 4

    return TestMarker(
        test_number=test_number,
        is_toc=is_toc,
        is_phantom=is_phantom,
    )
