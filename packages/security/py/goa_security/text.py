"""Text normalisation and fingerprinting shared by every security control."""

from __future__ import annotations

import hashlib
import re

# Control characters, plus the Unicode separators and zero-width characters that
# let one line of text render as several -- or hide inside another word.
#
# This matters more than it looks. A "fact" or a chat message that renders as two
# lines can close a data block and open what reads as a new instruction; a
# zero-width space between letters defeats a pattern match while leaving the text
# perfectly legible to the model. Both are stripped before anything else runs.
_CONTROL_AND_INVISIBLE = re.compile(
    "["
    "\x00-\x08\x0b-\x1f\x7f"  # C0 controls, keeping \t and \n to collapse below
    "­"                   # soft hyphen
    "​-‏"            # zero-width space/joiners, LTR/RTL marks
    "  "             # line/paragraph separators
    "‪-‮"            # bidi overrides
    "⁠-⁤"            # word joiner, invisible operators
    "﻿"                   # BOM / zero-width no-break space
    "]"
)

_WHITESPACE = re.compile(r"\s+")


def normalise_control_characters(value: str) -> str:
    """Strip invisible characters and collapse whitespace to single spaces.

    Runs before pattern matching, not after. "ig​nore previous instructions"
    reads normally to a model and does not match a naive regex; collapsing it
    first is what makes the pattern list worth having at all.
    """
    if not value:
        return ""
    stripped = _CONTROL_AND_INVISIBLE.sub("", value)
    return _WHITESPACE.sub(" ", stripped).strip()


def hash_input(value: str, length: int = 32) -> str:
    """Fingerprint untrusted input so it can be correlated but never read.

    The Python counterpart of the Gateway's middleware.HashInput, using the same
    algorithm and the same truncation so a single payload produces the same
    fingerprint in Go and in Python. That is the whole point: one attack seen by
    two services must be recognisable as one attack.
    """
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:length]
