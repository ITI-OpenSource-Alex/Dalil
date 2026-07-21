"""
app/ingestion/ocr_normalizer.py
--------------------------------
Deterministic, domain-agnostic OCR text normalizer.

Performs lossless text cleanup on raw OCR output. Every transformation is
deterministic and requires no knowledge of document structure or semantics.
Reusable for any OCR project.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

__all__ = [
    "OCRNormalizer",
    "DEFAULT_NORMALIZER",
    "normalize_unicode",
    "normalize_dashes",
    "normalize_quotes",
    "normalize_ellipsis",
    "remove_page_footers",
    "remove_publisher_headers",
    "remove_copyright",
    "remove_page_numbers",
    "normalize_bullets",
    "normalize_whitespace",
    "collapse_blank_lines",
]

NORMALIZED_BULLET = "•"

_WHITESPACE_RE = re.compile(r"[ \t]+")
_PAGE_FOOTER_RE = re.compile(r"^\s*[>\d\s]*\[?[QSB]?\s*p\.", re.IGNORECASE)
_PUBLISHER_HEADER_RE = re.compile(
    r"^\s*Cambridge\s+(?:IELTS|University\s+Press)", re.IGNORECASE
)
_COPYRIGHT_RE = re.compile(r"©|Copyright|Cambridge University Press", re.IGNORECASE)
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*$")
_BULLET_START_RE = re.compile(r"^[\*•·►\+\[]\s*")
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")


def _filter_lines(text: str, predicate: Callable[[str], bool]) -> str:
    """Keep only lines where predicate returns True."""
    return "\n".join(line for line in text.splitlines() if predicate(line))


def _map_lines(text: str, transform: Callable[[str], str]) -> str:
    """Apply transform to each line."""
    return "\n".join(transform(line) for line in text.splitlines())


def normalize_unicode(text: str) -> str:
    """NFC normalization, remove zero-width characters, NBSP to space."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")  # NBSP
    text = text.replace("\ufeff", "")  # BOM
    text = text.replace("\u200b", "")  # Zero-width space
    text = text.replace("\u200c", "")  # Zero-width non-joiner
    text = text.replace("\u200d", "")  # Zero-width joiner
    return text


def normalize_dashes(text: str) -> str:
    """Replace em-dash, en-dash, and minus sign with standard hyphen."""
    text = text.replace("—", "-")  # em-dash
    text = text.replace("–", "-")  # en-dash
    text = text.replace("−", "-")  # minus sign
    return text


def normalize_quotes(text: str) -> str:
    """Replace curly quotes with straight quotes."""
    text = text.replace("‘", "'")  # left single
    text = text.replace("’", "'")  # right single
    text = text.replace("“", '"')  # left double
    text = text.replace("”", '"')  # right double
    return text


def normalize_ellipsis(text: str) -> str:
    """Replace ellipsis character with three dots."""
    return text.replace("…", "...")


def remove_page_footers(text: str) -> str:
    """Remove lines matching common OCR page footer patterns."""
    return _filter_lines(text, lambda line: not _PAGE_FOOTER_RE.match(line))


def remove_publisher_headers(text: str) -> str:
    """Remove lines containing publisher header text."""
    return _filter_lines(text, lambda line: not _PUBLISHER_HEADER_RE.match(line))


def remove_copyright(text: str) -> str:
    """Remove lines containing copyright indicators."""
    return _filter_lines(text, lambda line: not _COPYRIGHT_RE.search(line))


def remove_page_numbers(text: str) -> str:
    """Remove lines that contain only a standalone page number (1-3 digits)."""
    return _filter_lines(text, lambda line: not _PAGE_NUMBER_RE.match(line))


def normalize_bullets(text: str) -> str:
    """Normalize various bullet characters at line start to unified bullet."""

    def _transform(line: str) -> str:
        if _BULLET_START_RE.match(line):
            return _BULLET_START_RE.sub(f"{NORMALIZED_BULLET} ", line)
        return line

    return _map_lines(text, _transform)


def normalize_whitespace(text: str) -> str:
    """Collapse multiple inline spaces/tabs to single space, strip trailing."""

    def _transform(line: str) -> str:
        return _WHITESPACE_RE.sub(" ", line).rstrip()

    return _map_lines(text, _transform)


def collapse_blank_lines(text: str) -> str:
    """Collapse 3+ consecutive blank lines to 2 blank lines."""
    return _BLANK_LINE_RE.sub("\n\n", text)


class OCRNormalizer:
    """Deterministic OCR text normalizer.

    Applies a pipeline of independent, pure text-cleaning functions.
    """

    _PIPELINE: tuple[Callable[[str], str], ...] = (
        normalize_unicode,
        normalize_dashes,
        normalize_quotes,
        normalize_ellipsis,
        remove_page_footers,
        remove_publisher_headers,
        remove_copyright,
        remove_page_numbers,
        normalize_bullets,
        normalize_whitespace,
        collapse_blank_lines,
    )

    def normalize(self, text: str) -> str:
        """Run the full normalization pipeline on text."""
        for transform in self._PIPELINE:
            text = transform(text)
        return text


DEFAULT_NORMALIZER = OCRNormalizer()
