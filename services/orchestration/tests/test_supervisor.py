import pytest
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
    """Turn 1 has nothing to resolve against and must not break."""
    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 1, "output_tokens": 1}}
    mock_llm.return_value = {
        "parsed": IntentResult(intent="RAG", confidence=0.9),
        "raw": raw_mock,
    }

    result = await classify_intent("What is IELTS?", history=None)

    assert result.intent == "RAG"
    sent = mock_llm.call_args[0][0]
    assert len(sent) == 2
    # No rewrite offered, so callers fall back to the raw message.
    assert result.standalone_question == ""


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
