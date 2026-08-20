from app.services.supervisor import classify_intent, IntentResult

from unittest.mock import MagicMock

async def test_classify_intent_writing(mock_llm):
    """Verify 'evaluate my essay' is classified as WRITING."""
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm.return_value = {"parsed": IntentResult(intent="WRITING", confidence=0.98), "raw": raw_mock}
    
    result = await classify_intent("evaluate my essay")
    
    assert result.intent == "WRITING"
    assert result.confidence == 0.98
    mock_llm.assert_called_once()

async def test_classify_intent_opportunity(mock_llm):
    """Verify 'find scholarships in Germany' is classified as OPPORTUNITY_SEARCH."""
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm.return_value = {"parsed": IntentResult(intent="OPPORTUNITY_SEARCH", confidence=0.95), "raw": raw_mock}
    
    result = await classify_intent("find scholarships in Germany")
    
    assert result.intent == "OPPORTUNITY_SEARCH"
    assert result.confidence == 0.95
    mock_llm.assert_called_once()

async def test_classify_intent_speaking(mock_llm):
    """Verify 'I want to practice IELTS speaking' is classified as SPEAKING."""
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm.return_value = {"parsed": IntentResult(intent="SPEAKING", confidence=0.99), "raw": raw_mock}
    
    result = await classify_intent("I want to practice IELTS speaking")
    
    assert result.intent == "SPEAKING"
    assert result.confidence == 0.99
    mock_llm.assert_called_once()

# ---------------------------------------------------------------------------
# History wiring (BUG-017)
#
# Memory was written by save_context and served correctly by
# GET /sessions/{id}/history, but chat.py called load_memory_variables and
# discarded the result, so no history ever reached a request. Every
# conversation was stateless and turn 2 could not resolve "it".
# ---------------------------------------------------------------------------


class _Msg:
    """Minimal stand-in for a LangChain message (has .type and .content)."""

    def __init__(self, type_: str, content: str) -> None:
        self.type = type_
        self.content = content


async def test_history_is_sent_to_the_llm(mock_llm):
    """The supervisor must actually receive prior turns.

    Asserting on the messages passed to the LLM rather than on the result is
    deliberate: a mocked LLM returns whatever it is told to, so a test that only
    checked the return value would pass even if history were dropped again --
    which is the exact shape of the original bug.
    """
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm.return_value = {
        "parsed": IntentResult(intent="RAG", confidence=0.9),
        "raw": raw_mock,
    }

    history = [
        _Msg("human", "What band does the Potsdam Data Science master require?"),
        _Msg("ai", "It requires 6.5 overall."),
    ]

    await classify_intent("Is my score high enough for it?", history=history)

    sent = mock_llm.call_args[0][0]
    contents = [m["content"] for m in sent]
    assert any("Potsdam" in c for c in contents), (
        "prior turns never reached the supervisor; history was dropped"
    )
    # System prompt, two history turns, then the live message, in that order.
    assert sent[0]["role"] == "system"
    assert sent[-1]["content"] == "Is my score high enough for it?"
    assert [m["role"] for m in sent[1:-1]] == ["user", "assistant"]


async def test_history_is_trimmed_to_recent_turns(mock_llm):
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 1, "output_tokens": 1}}
    mock_llm.return_value = {
        "parsed": IntentResult(intent="RAG", confidence=0.9),
        "raw": raw_mock,
    }

    history = [_Msg("human", f"turn {i}") for i in range(20)]
    await classify_intent("latest", history=history)

    sent = mock_llm.call_args[0][0]
    # system + 6 trimmed turns + live message
    assert len(sent) == 8
    assert "turn 19" in sent[-2]["content"]


async def test_no_history_still_classifies(mock_llm):
    """A self-contained factual turn uses the deterministic fast path."""

    result = await classify_intent("What is IELTS?", history=None)

    assert result.intent == "RAG"
    assert result.confidence == 0.99
    assert result.standalone_question == "What is IELTS?"
    mock_llm.assert_not_called()


async def test_context_dependent_rag_question_still_uses_model(mock_llm):
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 1, "output_tokens": 1}}
    mock_llm.return_value = {
        "parsed": IntentResult(
            intent="RAG",
            confidence=0.9,
            standalone_question="What IELTS score does Potsdam require?",
        ),
        "raw": raw_mock,
    }

    result = await classify_intent(
        "What score does it require?",
        history=[_Msg("human", "Tell me about Potsdam admissions")],
    )

    assert result.standalone_question == "What IELTS score does Potsdam require?"
    mock_llm.assert_called_once()


async def test_cost_telemetry_does_not_block_the_event_loop(mock_llm, monkeypatch):
    """Token accounting must never stall concurrent chat turns.

    record_llm_cost uses the *synchronous* redis client with a 2s connect
    timeout. Called inline from this coroutine it blocks the whole event loop --
    every other in-flight chat, the health check, everything -- for as long as
    redis-gateway takes to answer. With that host absent it measured ~4s per
    call, on the request path of every turn.

    Asserted behaviourally rather than by inspecting how the call is made: two
    classifications, each with a telemetry call that sleeps synchronously, must
    finish in roughly the time of one. Inline, they serialise and take twice as
    long.
    """
    import asyncio
    import time as _time

    import app.telemetry

    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm.return_value = {
        "parsed": IntentResult(intent="RAG", confidence=0.9),
        "raw": raw_mock,
    }

    # Two 0.5s sleeps: concurrent is ~0.5s, serialised is ~1.0s. The gap is wide
    # enough in absolute terms that a loaded CI runner cannot turn a pass into a
    # failure, which a tighter budget could.
    delay = 0.5

    def slow_record(*args, **kwargs):
        _time.sleep(delay)

    monkeypatch.setattr(app.telemetry, "record_llm_cost", slow_record)

    started = _time.perf_counter()
    await asyncio.gather(
        classify_intent("I need some guidance about studying abroad"),
        classify_intent("Help me decide what to do next"),
    )
    elapsed = _time.perf_counter() - started

    assert elapsed < delay * 1.5, (
        f"two turns took {elapsed:.2f}s for {delay}s of telemetry each -- "
        "the telemetry call is blocking the event loop"
    )


async def test_fallback_result_carries_no_rewrite(mock_llm):
    """A classifier failure must not silently substitute an empty message.

    standalone_question defaults to "" so chat.py's
    `intent_result.standalone_question or request.message` keeps the user's
    words when classification falls back.
    """
    mock_llm.side_effect = RuntimeError("provider down")

    result = await classify_intent("Is my score high enough for it?")

    assert result.is_fallback is True
    assert result.standalone_question == ""
