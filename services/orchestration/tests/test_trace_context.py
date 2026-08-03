from app.core.trace_context import build_traceparent


def test_build_traceparent_uses_w3c_format():
    value = build_traceparent("a" * 32, "b" * 16)

    assert value == f"00-{'a' * 32}-{'b' * 16}-01"


def test_build_traceparent_rejects_missing_malformed_and_zero_ids():
    assert build_traceparent(None, "b" * 16) is None
    assert build_traceparent("not-a-trace", "b" * 16) is None
    assert build_traceparent("0" * 32, "b" * 16) is None
    assert build_traceparent("a" * 32, "0" * 16) is None
