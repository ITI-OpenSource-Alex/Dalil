"""Shared security primitives for GOA's Python services (GOA-034).

One copy, deliberately. Four services need the same injection patterns and the
same PII rules, and a pattern list that exists in four places is a pattern list
that will be updated in three of them. The one you miss is a silent hole, and
nothing will tell you which one it was.

Distributed the way packages/contracts/py already is: each service's Dockerfile
copies this directory in, and the build context is the repository root. See
services/ingestion/Dockerfile for the precedent.

Nothing here is a guarantee. An LLM has no equivalent of a parameterised query
-- system prompt, retrieved documents and user text all arrive as one
undifferentiated stream of tokens, so every control in this package reduces
probability rather than eliminating risk. Read `docs/security/threat-model.md`
before assuming otherwise.
"""

from goa_security.patterns import (
    INJECTION_PATTERNS,
    contains_injection,
    describe_injection,
)
from goa_security.pii import PII_PATTERNS, has_pii, redact_pii
from goa_security.prompts import (
    UNTRUSTED_DATA_FOOTER,
    UNTRUSTED_DATA_HEADER,
    wrap_untrusted,
)
from goa_security.text import hash_input, normalise_control_characters

__all__ = [
    "INJECTION_PATTERNS",
    "PII_PATTERNS",
    "UNTRUSTED_DATA_FOOTER",
    "UNTRUSTED_DATA_HEADER",
    "contains_injection",
    "describe_injection",
    "has_pii",
    "hash_input",
    "normalise_control_characters",
    "redact_pii",
    "wrap_untrusted",
]
