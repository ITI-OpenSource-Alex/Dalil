import re
from typing import Optional


_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def build_traceparent(
    trace_id: Optional[str],
    parent_span_id: Optional[str],
    *,
    sampled: bool = True,
) -> Optional[str]:
    """Build the W3C trace context carrier used at GOA service boundaries."""
    if not trace_id or not parent_span_id:
        return None

    normalized_trace_id = trace_id.lower()
    normalized_span_id = parent_span_id.lower()
    if (
        not _TRACE_ID_RE.fullmatch(normalized_trace_id)
        or normalized_trace_id == "0" * 32
        or not _SPAN_ID_RE.fullmatch(normalized_span_id)
        or normalized_span_id == "0" * 16
    ):
        return None

    flags = "01" if sampled else "00"
    return f"00-{normalized_trace_id}-{normalized_span_id}-{flags}"
