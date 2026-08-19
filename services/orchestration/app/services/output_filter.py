"""Filtering what goes back to the user (GOA-034, OWASP LLM02/LLM06).

The awkward part of this ticket: chat is streamed, and you cannot un-send the
first half of an answer. Three options were considered and one of them is a lie:

  Buffer everything, then filter. Airtight, and it destroys the streaming that
  GOA-096's ORC-08 exists to protect -- the user watches nothing happen for
  8-20 seconds instead of reading as it arrives.

  Sliding window over the stream. Keeps streaming, catches most spans, and
  quietly misses anything straddling the window boundary. A partial guarantee
  that reads like a total one is worse than a documented gap.

  Filter where the text is still whole. What GOA actually does.

The third works because of a detail of this system: RAG returns its complete
answer to orchestration, which *then* slices it into five-character chunks
(client.py). For the RAG, CV_REVIEW and EXAM_PREP intents the full text is in
memory before a single token leaves, so it can be filtered with no streaming
cost at all.

WRITING and SPEAKING are genuinely token-by-token from their own services and
are not covered here. That gap is real, is recorded in the threat model, and
belongs to those services rather than to this one.
"""

from __future__ import annotations

from typing import Optional

import structlog
from goa_security import detect_prompt_leak, hash_input, redact_pii

from app.core.metrics import (
    goa_security_pii_redactions_total,
    goa_security_prompt_leaks_total,
)

logger = structlog.get_logger("orchestration.output_filter")


def filter_response(
    answer: str,
    user_id: str,
    correlation_id: Optional[str],
    intent: str,
    leak_fragments: tuple[str, ...] = (),
) -> str:
    """Redact PII and refuse to return a leaked system prompt.

    Returns the text to send. Never raises: an exception here would turn a
    successful answer into a failed request, which is the wrong trade for a
    control whose job is to make a good answer safer.
    """
    if not answer:
        return answer

    filtered, found = redact_pii(answer)
    if found:
        for label in found:
            goa_security_pii_redactions_total.labels(pii_type=label).inc()
        # Labels only. Writing the matched values into the log would move the
        # PII from a response nobody stored into a log that ships to an
        # aggregator -- the exact harm this function exists to prevent.
        logger.warning(
            "SECURITY_EVENT",
            event_type="pii_redacted",
            severity="MEDIUM",
            user_id=user_id,
            correlation_id=correlation_id,
            input_hash=hash_input(answer),
            action_taken="redacted",
            pii_types=found,
            intent=intent,
        )

    leaked = detect_prompt_leak(filtered, leak_fragments)
    if leaked:
        goa_security_prompt_leaks_total.inc()
        logger.warning(
            "SECURITY_EVENT",
            event_type="system_prompt_leak",
            # LOW on purpose. A system prompt is not a credential; knowing GOA
            # routes into six intents unlocks nothing. This is worth seeing, not
            # worth waking anyone for, and inflating it would train us to ignore
            # our own alerts.
            severity="LOW",
            user_id=user_id,
            correlation_id=correlation_id,
            input_hash=hash_input(answer),
            action_taken="response_replaced",
            intent=intent,
        )
        return (
            "I can't share my internal instructions, but I'm happy to help with "
            "your study-abroad question."
        )

    return filtered
