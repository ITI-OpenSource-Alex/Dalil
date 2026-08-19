"""System prompt leakage detection (part of OWASP LLM01/LLM07).

An honest note on severity, because it decides how much this deserves.

A system prompt is not a credential. Knowing that GOA's supervisor routes into
six intents unlocks nothing: no data, no account, no privilege. The real harms
are that a competitor copies prompt engineering, and that a successful
extraction is a signal other instructions might also be extractable. Both are
worth knowing about. Neither is an emergency.

So this is logged at LOW severity and deliberately not treated as an incident.
Correctly ranking a risk as low is a security skill; inflating it to look
thorough trains you to ignore your own alerts.

The detection itself is the reliable half of the control. Asking a model not to
reveal its instructions is a request it can be talked out of; checking the
output for distinctive fragments is deterministic.
"""

from __future__ import annotations

from typing import Iterable, Optional

from goa_security.text import normalise_control_characters

# Below this length a "fragment" matches ordinary prose by accident. "You are a"
# appears in a great many innocent sentences; a full clause does not.
MIN_FRAGMENT_LENGTH = 25


def canary_fragments(system_prompt: str, min_words: int = 6) -> tuple[str, ...]:
    """Pick distinctive lines from a system prompt to watch for in responses.

    Lines, rather than a sliding window of n-grams: a model reproducing its
    instructions reproduces them line by line, and lines are cheap to compare.

    Short lines and lines that are mostly punctuation are dropped -- they are
    the ones that collide with normal text and produce false positives on
    perfectly good answers.
    """
    fragments = []
    for line in system_prompt.splitlines():
        candidate = normalise_control_characters(line)
        if len(candidate) < MIN_FRAGMENT_LENGTH:
            continue
        if len(candidate.split()) < min_words:
            continue
        if not any(character.isalpha() for character in candidate):
            continue
        fragments.append(candidate)
    return tuple(fragments)


def detect_prompt_leak(
    response: str, fragments: Iterable[str], min_matches: int = 1
) -> Optional[str]:
    """Return the first system-prompt fragment found in the response, or None.

    Normalises whitespace on both sides before comparing: a model that echoes
    its instructions often reflows them, and a comparison that breaks on a
    different line wrap would catch only the laziest possible leak.

    `min_matches` exists for callers who want to require corroboration before
    acting. One matched clause is usually enough to be interesting; requiring
    two makes the signal stronger at the cost of missing a partial leak.
    """
    if not response:
        return None

    haystack = normalise_control_characters(response).lower()
    matched = []
    for fragment in fragments:
        needle = normalise_control_characters(fragment).lower()
        if len(needle) < MIN_FRAGMENT_LENGTH:
            continue
        if needle in haystack:
            matched.append(fragment)
            if len(matched) >= min_matches:
                return matched[0]
    return None
