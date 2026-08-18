"""Deterministic, provenance-aware cleanup for OCR-sourced essays.

The Writing UI and Exam service normally submit typed text.  Applying OCR fixes
to that text would erase real candidate mistakes, so normalization is opt-in via
``inputSource="ocr"``.  Every normalized character retains its source offset so
feedback generated against the cleaned text can still underline the original.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


InputSource = Literal["typed", "ocr"]


@dataclass(frozen=True)
class NormalizationChange:
    start_char: int
    end_char: int
    original: str
    replacement: str
    rule: str


@dataclass(frozen=True)
class NormalizedEssay:
    original_text: str
    text: str
    source_offsets: tuple[int, ...]
    changes: tuple[NormalizationChange, ...]

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a half-open normalized span back to the submitted source text."""
        if start < 0 or end <= start or end > len(self.source_offsets):
            raise ValueError("normalized span is outside the essay")
        offsets = self.source_offsets[start:end]
        return min(offsets), max(offsets) + 1


_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u00ad"}
_OCR_WORDS = {
    "s0": "so",
    "0f": "of",
    "t0": "to",
    "d0": "do",
    "n0": "no",
}


def _identity(text: str) -> NormalizedEssay:
    return NormalizedEssay(text, text, tuple(range(len(text))), ())


def normalize_essay(text: str, source: InputSource = "typed") -> NormalizedEssay:
    """Normalize only unambiguous OCR artifacts and preserve source offsets.

    This deliberately does not use a dictionary, spell checker, or language
    model.  Candidate spelling, grammar, punctuation, and word choice remain
    untouched.  The same input always produces byte-for-byte identical output.
    """
    if source == "typed":
        return _identity(text)
    if source != "ocr":
        raise ValueError(f"unsupported essay input source: {source}")

    chars: list[str] = []
    offsets: list[int] = []
    changes: list[NormalizationChange] = []

    # Unicode compatibility normalization fixes ligatures/full-width glyphs.
    for index, char in enumerate(text):
        if char in _ZERO_WIDTH:
            changes.append(NormalizationChange(index, index + 1, char, "", "invisible"))
            continue
        replacement = unicodedata.normalize("NFKC", char)
        if replacement != char:
            changes.append(
                NormalizationChange(index, index + 1, char, replacement, "unicode_nfkc")
            )
        for output_char in replacement:
            chars.append(output_char)
            offsets.append(index)

    interim = "".join(chars).replace("\r\n", "\n").replace("\r", "\n")
    # Rebuild CR offsets after newline canonicalisation.
    if "\r" in "".join(chars):
        rebuilt_chars: list[str] = []
        rebuilt_offsets: list[int] = []
        cursor = 0
        while cursor < len(chars):
            if chars[cursor] == "\r":
                rebuilt_chars.append("\n")
                rebuilt_offsets.append(offsets[cursor])
                if cursor + 1 < len(chars) and chars[cursor + 1] == "\n":
                    cursor += 1
            else:
                rebuilt_chars.append(chars[cursor])
                rebuilt_offsets.append(offsets[cursor])
            cursor += 1
        chars, offsets = rebuilt_chars, rebuilt_offsets
        interim = "".join(chars)

    def replace_matches(pattern: re.Pattern[str], replacement, rule: str) -> None:
        nonlocal chars, offsets, interim
        new_chars: list[str] = []
        new_offsets: list[int] = []
        cursor = 0
        for match in pattern.finditer(interim):
            new_chars.extend(chars[cursor : match.start()])
            new_offsets.extend(offsets[cursor : match.start()])
            value = replacement(match) if callable(replacement) else replacement
            anchor = offsets[match.start()]
            new_chars.extend(value)
            new_offsets.extend([anchor] * len(value))
            original_start = min(offsets[match.start() : match.end()])
            original_end = max(offsets[match.start() : match.end()]) + 1
            original = text[original_start:original_end]
            if original != value:
                changes.append(
                    NormalizationChange(
                        original_start, original_end, original, value, rule
                    )
                )
            cursor = match.end()
        new_chars.extend(chars[cursor:])
        new_offsets.extend(offsets[cursor:])
        chars, offsets = new_chars, new_offsets
        interim = "".join(chars)

    # Remove line-wrap hyphenation only for lower-case word fragments.
    replace_matches(
        re.compile(r"(?<=[a-z])-\s*\n\s*(?=[a-z])"), "", "line_wrap_hyphen"
    )
    # A lone vertical bar is a common OCR rendering of the pronoun "I".
    replace_matches(re.compile(r"(?<!\w)\|(?!\w)"), "I", "standalone_pipe")

    def replace_known_word(match: re.Match[str]) -> str:
        word = match.group(0)
        return _OCR_WORDS[word.lower()].upper() if word.isupper() else _OCR_WORDS[word.lower()]

    replace_matches(
        re.compile(r"\b(?:s0|0f|t0|d0|n0)\b", re.IGNORECASE),
        replace_known_word,
        "known_digit_confusion",
    )
    # Preserve paragraph breaks but collapse OCR line wrapping and repeated spaces.
    replace_matches(re.compile(r"[ \t]+"), " ", "horizontal_whitespace")
    replace_matches(re.compile(r" *\n(?: *\n)+ *"), "\n\n", "paragraph_break")
    replace_matches(re.compile(r"(?<!\n)\n(?!\n)"), " ", "wrapped_line")

    # Trim without losing the mapping used for inline feedback.
    leading = len(interim) - len(interim.lstrip())
    trailing = len(interim.rstrip())
    if leading or trailing != len(interim):
        chars = chars[leading:trailing]
        offsets = offsets[leading:trailing]
        interim = "".join(chars)

    return NormalizedEssay(
        original_text=text,
        text=interim,
        source_offsets=tuple(offsets),
        changes=tuple(changes),
    )
