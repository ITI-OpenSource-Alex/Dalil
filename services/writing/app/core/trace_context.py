import re
from typing import Optional, TypedDict


class LangfuseTraceContext(TypedDict):
    trace_id: str
    parent_span_id: str


_TRACEPARENT_RE = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)


def parse_traceparent(value: Optional[str]) -> Optional[LangfuseTraceContext]:
    """Return Langfuse v4 trace context or None for absent/malformed carriers."""
    if not value:
        return None

    match = _TRACEPARENT_RE.fullmatch(value.strip().lower())
    if match is None:
        return None

    trace_id, parent_span_id, _flags = match.groups()
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        return None

    return {
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
    }
