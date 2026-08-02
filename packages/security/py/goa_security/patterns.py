"""Prompt-injection pattern matching (OWASP LLM01).

> [!IMPORTANT]
> Read this before trusting anything in this module.
>
> A regex list does not stop prompt injection. It never has. Every one of these
> patterns is defeated by paraphrase, by character substitution ("1gnore"), by
> base64, by a language other than English, or by splitting the instruction
> across two turns. A determined attacker walks through it.
>
> It is here for three reasons that are real:
>
>  1. It stops the copy-pasted 95%. Most attempts against a student project are
>     jailbreaks lifted verbatim from a forum, and those match exactly.
>  2. It produces a signal. Every match increments a counter and writes a log
>     line, so "we are being probed" becomes something you know rather than
>     something you assume. Detection has value even when prevention fails.
>  3. It is one layer of several. Combined with the data-not-instructions
>     wrapper in prompts.py and output filtering, it raises cost.
>
> The layer that actually does the most work is prompts.wrap_untrusted, not this
> one. If you are choosing where to spend effort, spend it there.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from goa_security.text import normalise_control_characters


class InjectionPattern(NamedTuple):
    name: str
    regex: re.Pattern[str]


# Ordered roughly by how often each is seen in the wild.
#
# Every pattern here is deliberately anchored to phrasing that has no place in a
# genuine question about studying abroad. The false-positive risk is real and is
# tested: "please ignore my previous message, I meant Germany not Austria" is an
# ordinary thing for a user to type and must NOT match.
INJECTION_PATTERNS: tuple[InjectionPattern, ...] = (
    InjectionPattern(
        "ignore_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.]{0,30}?"
            r"\b(previous|prior|earlier|above|all|any|your)\b[^.]{0,20}?"
            r"\b(instruction|instructions|prompt|prompts|rule|rules|direction|directions|guideline|guidelines|context)\b",
            re.IGNORECASE,
        ),
    ),
    InjectionPattern(
        "role_reassignment",
        re.compile(
            r"\byou\s+are\s+(now|no\s+longer|actually)\b"
            r"|\bact\s+as\s+(if\s+you\s+are\s+)?(a|an|the)\b"
            r"|\bpretend\s+(to\s+be|you\s+are)\b"
            r"|\bfrom\s+now\s+on[, ]+you\b",
            re.IGNORECASE,
        ),
    ),
    InjectionPattern(
        "system_prompt_extraction",
        re.compile(
            r"\b(reveal|repeat|print|show|display|output|tell\s+me)\b[^.]{0,40}?"
            r"\b(system\s+prompt|initial\s+instructions|your\s+instructions|prompt\s+above|everything\s+above)\b"
            r"|\bwhat\s+(were|are)\s+your\s+(original\s+)?instructions\b"
            r"|\brepeat\s+everything\s+above\b",
            re.IGNORECASE,
        ),
    ),
    InjectionPattern(
        "role_marker_injection",
        # Chat-format markers. A user has no reason to type these; a payload
        # trying to forge a turn boundary has every reason to.
        re.compile(
            r"^\s*(system|assistant|human|user)\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    InjectionPattern(
        "delimiter_injection",
        # Attempts to close a data block and open something that reads as
        # instructions -- the attack prompts.wrap_untrusted is defending against.
        re.compile(
            r"</?\s*(system|instruction|instructions|prompt)\s*>"
            r"|-{3,}\s*(end\s+of|system|instruction)"
            r"|\[/?(INST|SYS|SYSTEM)\]",
            re.IGNORECASE,
        ),
    ),
    InjectionPattern(
        "jailbreak_persona",
        re.compile(
            r"\bDAN\b\s+(mode|prompt)"
            r"|\bdeveloper\s+mode\b"
            r"|\bjailbreak\b"
            r"|\bwithout\s+(any\s+)?(restrictions|filters|limitations|guidelines)\b"
            r"|\bno\s+longer\s+bound\s+by\b",
            re.IGNORECASE,
        ),
    ),
    InjectionPattern(
        "encoded_payload",
        # Not an attack on its own -- a flag. A long base64 run in a question
        # about visas is not something a student types by accident, and the
        # model will happily decode what a regex cannot read.
        re.compile(r"\b[A-Za-z0-9+/]{60,}={0,2}\b"),
    ),
)


def describe_injection(value: str) -> Optional[str]:
    """Return the name of the first matching pattern, or None.

    Normalises invisible characters first: a zero-width space between two
    letters is invisible to the reader, meaningless to the model, and fatal to a
    naive regex.
    """
    if not value:
        return None

    candidate = normalise_control_characters(value)
    for pattern in INJECTION_PATTERNS:
        if pattern.regex.search(candidate):
            return pattern.name
    return None


def contains_injection(value: str) -> bool:
    """True when the text matches any known injection pattern."""
    return describe_injection(value) is not None
