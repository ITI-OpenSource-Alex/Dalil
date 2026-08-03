"""Everything an extracted fact must survive before it is allowed to persist.

A stored fact is not ordinary data. It is attacker-controlled text that gets
pasted into a system prompt on every subsequent turn for the next thirty days --
stored prompt injection with a long fuse, and the most durable injection surface
in the system. The user types once; the payload is replayed into the model
indefinitely.

So the trust boundary is here, on the way in, not on the way out. GOA-034 owns
the OWASP LLM controls generally and scans model *outputs* for PII; this is the
input side, which that ticket does not currently cover. The two should be
reconciled -- see the plan's cohesion section -- but a fact table that waits for
another ticket before sanitising is a fact table that has already stored the
payload.

Nothing here trusts the extraction model to have behaved. It ran on
attacker-influenced input, so its output is attacker-influenced too.
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

from app.core.metrics import goa_orchestration_facts_rejected_total
from app.schemas.facts import FactCandidate

logger = structlog.get_logger("orchestration.fact_sanitizer")

MAX_FACT_LENGTH = 200

# Instruction-shaped content. A fact is a noun phrase about the user -- "BSc in
# Electrical Engineering", "Germany", "worried about funding". None of these
# patterns can appear in one, so anything carrying them is not a fact.
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)",
        r"disregard\s+(all\s+|any\s+)?(previous|prior|above|earlier)",
        r"forget\s+(everything|all|your)\s+",
        r"\b(system|assistant|user)\s*:",
        r"you\s+are\s+(now|no\s+longer)\b",
        r"new\s+(instructions?|rules?|persona)",
        r"</?\s*(system|instructions?|prompt)",
        r"\bprompt\b.{0,20}\b(reveal|repeat|print|show|leak)",
        r"\b(reveal|repeat|print|show|leak)\b.{0,20}\bprompt\b",
        r"```",
    )
]

# Deliberately conservative. Redacting a real GPA because it looked like a phone
# number costs one fact; storing someone's national ID for thirty days is a
# different kind of mistake.
_PII_PATTERNS = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,14}\d(?!\d)")),
    ("national_id", re.compile(r"(?<!\d)\d{14}(?!\d)")),
    ("passport", re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")),
]

# Control characters and the Unicode separators that let one line of text render
# as several -- a fact rendered as two lines in a prompt can close the data block
# and open an instruction.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f  ]")


def _reject(reason: str, fact_type: str) -> None:
    goa_orchestration_facts_rejected_total.labels(reason=reason).inc()
    logger.warning(
        "Rejected extracted fact",
        reason=reason,
        fact_type=fact_type,
        # The value itself is never logged. It is the untrusted content, and
        # a log line is read by humans and shipped to aggregators.
    )


def redact_pii(value: str) -> tuple[str, bool]:
    """Replace PII spans with a marker. Returns the value and whether anything hit."""
    redacted = value
    hit = False
    for label, pattern in _PII_PATTERNS:
        redacted, count = pattern.subn(f"[redacted-{label}]", redacted)
        hit = hit or count > 0
    return redacted, hit


def sanitize(fact_type: str, value: str, confidence: float, session_id: Optional[str]) -> Optional[FactCandidate]:
    """Turn a model-proposed value into a storable fact, or reject it.

    Returns None when the value must not be stored. Every rejection is counted
    by reason, so "the model started emitting junk" is visible on a dashboard
    rather than inferred from an empty table.
    """
    if value is None:
        return None

    cleaned = _CONTROL_CHARS.sub(" ", str(value)).strip()
    if not cleaned:
        return None

    if len(cleaned) > MAX_FACT_LENGTH:
        # Truncation is not an option here. A truncated injection payload is
        # still an injection payload, and a truncated fact is a wrong fact.
        _reject("too_long", fact_type)
        return None

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            _reject("injection", fact_type)
            return None

    cleaned, had_pii = redact_pii(cleaned)
    if had_pii:
        # Counted but kept: "worried about affording [redacted-phone]" is still a
        # usable concern, and dropping the whole fact would quietly punish users
        # who happen to mention a number.
        goa_orchestration_facts_rejected_total.labels(reason="pii").inc()
        logger.info("Redacted PII from extracted fact", fact_type=fact_type)

    if not cleaned.strip() or cleaned.strip().startswith("[redacted-"):
        # Nothing survived redaction but the marker.
        return None

    try:
        return FactCandidate(
            fact_type=fact_type,
            fact_value=cleaned.strip(),
            confidence=confidence,
            source_session=session_id,
        )
    except Exception:
        # Includes the fact_type allow-list: a model that invents 'ielts_band'
        # is refused here, and again by the CHECK constraint if it ever got past.
        _reject("invalid_type", fact_type)
        return None
