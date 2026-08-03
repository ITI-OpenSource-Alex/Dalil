from app.core.trace_context import parse_traceparent


def test_parse_traceparent_returns_langfuse_context():
    trace_id = "a" * 32
    span_id = "b" * 16

    assert parse_traceparent(f"00-{trace_id}-{span_id}-01") == {
        "trace_id": trace_id,
        "parent_span_id": span_id,
    }


def test_parse_traceparent_falls_back_for_absent_or_malformed_values():
    assert parse_traceparent(None) is None
    assert parse_traceparent("") is None
    assert parse_traceparent("malformed") is None
    assert parse_traceparent(f"00-{'0' * 32}-{'b' * 16}-01") is None
    assert parse_traceparent(f"00-{'a' * 32}-{'0' * 16}-01") is None
