from unittest.mock import MagicMock

from app.core.trace_context import parse_traceparent
from app.observability import start_evaluation_trace


def test_parse_traceparent_returns_langfuse_context():
    trace_id = "a" * 32
    span_id = "b" * 16

    assert parse_traceparent(f"00-{trace_id}-{span_id}-01") == {
        "trace_id": trace_id,
        "parent_span_id": span_id,
    }


def test_start_evaluation_trace_attaches_to_parent():
    client = MagicMock()
    traceparent = f"00-{'a' * 32}-{'b' * 16}-01"

    start_evaluation_trace(
        client,
        user_id="user-1",
        essay_id=42,
        task_type="task2",
        from_cache=False,
        traceparent=traceparent,
    )

    assert client.start_observation.call_args.kwargs["trace_context"] == {
        "trace_id": "a" * 32,
        "parent_span_id": "b" * 16,
    }


def test_start_evaluation_trace_roots_on_malformed_header():
    client = MagicMock()

    start_evaluation_trace(
        client,
        user_id="user-1",
        essay_id=42,
        task_type="task2",
        from_cache=False,
        traceparent="malformed",
    )

    assert client.start_observation.call_args.kwargs["trace_context"] is None
