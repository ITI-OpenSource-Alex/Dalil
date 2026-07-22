"""Gateway integration tests for intent classification.

Cost model (these tests hit a paid gateway when live):

- Default (`pytest`): replays committed cassettes from tests/cassettes/ —
  zero network calls, zero cost, deterministic. This is what CI runs.
- `RUN_LIVE_LLM_TESTS=1 pytest tests/test_agentrouter.py`: re-records every
  cassette against the real gateway (~9 calls).
- `RUN_LIVE_LLM_TESTS=1 pytest -m smoke tests/test_agentrouter.py`: single
  live canary call — the day-to-day "is the gateway still up" check.

After changing SUPERVISOR_PROMPT or the IntentResult schema, re-record
(the cassettes hold the old prompt) and commit the updated cassettes.
"""

import os

import pytest

from app.services.supervisor import classify_intent, IntentResult, structured_llm

LIVE = os.getenv("RUN_LIVE_LLM_TESTS") == "1"

_PLACEHOLDER_KEYS = (None, "", "not-configured", "dummy-key")
_has_token = (
    os.getenv("ANTHROPIC_AUTH_TOKEN") not in _PLACEHOLDER_KEYS
    or os.getenv("ANTHROPIC_API_KEY") not in _PLACEHOLDER_KEYS
)

live_requires_token = pytest.mark.skipif(
    LIVE and not _has_token,
    reason="RUN_LIVE_LLM_TESTS=1 requires a valid ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY",
)


@pytest.mark.vcr
@live_requires_token
@pytest.mark.asyncio
async def test_structured_output_returns_intentresult_instance():
    result = await structured_llm.ainvoke(
        [{"role": "user", "content": "I want to practice speaking"}]
    )
    assert isinstance(result, (IntentResult, dict))


@pytest.mark.vcr
@live_requires_token
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, expected_intent",
    [
        pytest.param("What are the IELTS band requirements?", "RAG", id="rag-bands"),
        pytest.param(
            "Score my essay please",
            "WRITING",
            id="writing-smoke",
            # The historically flakiest utterance makes the best canary.
            marks=pytest.mark.smoke,
        ),
        pytest.param("Find me a masters in Germany", "OPPORTUNITY_SEARCH", id="opportunity"),
        pytest.param("How do I get a student visa?", "RAG", id="rag-visa"),
        pytest.param("hello", "RAG", id="fallback-general"),
        pytest.param("I want to practice IELTS speaking", "SPEAKING", id="speaking"),
        pytest.param("Can you review my CV?", "CV_REVIEW", id="cv-review"),
    ],
)
async def test_all_five_intents_classify_correctly(message, expected_intent):
    result = await classify_intent(message)
    assert result.intent == expected_intent


def test_base_url_omitted_when_setting_empty(mocker):
    mock_chat = mocker.patch("langchain_anthropic.ChatAnthropic")
    import app.core.config
    mocker.patch.object(app.core.config.settings, "anthropic_base_url", "")

    import importlib
    import app.services.supervisor
    importlib.reload(app.services.supervisor)

    mock_chat.assert_called_once()
    kwargs = mock_chat.call_args[1]
    assert "base_url" not in kwargs
