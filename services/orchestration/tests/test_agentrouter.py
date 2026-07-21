import pytest
from app.services.supervisor import classify_intent, IntentResult, structured_llm

import os

@pytest.mark.skipif(
    (not os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY") == "not-configured") and 
    (not os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_AUTH_TOKEN") == "not-configured"), 
    reason="Requires either ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN"
)
@pytest.mark.asyncio
async def test_structured_output_returns_intentresult_instance():
    result = await structured_llm.ainvoke([{"role": "user", "content": "I want to practice speaking"}])
    assert isinstance(result, (IntentResult, dict))

@pytest.mark.skipif(
    (not os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY") == "not-configured") and 
    (not os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_AUTH_TOKEN") == "not-configured"), 
    reason="Requires either ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN"
)
@pytest.mark.asyncio
@pytest.mark.parametrize("message, expected_intent", [
    ("What are the IELTS band requirements?", "RAG"),
    ("Score my essay please", "WRITING"),
    ("Find me a masters in Germany", "OPPORTUNITY_SEARCH"),
    ("How do I get a student visa?", "RAG"),
    ("hello", "RAG"), # fallback/general goes to RAG
    ("I want to practice IELTS speaking", "SPEAKING"),
    ("Can you review my CV?", "CV_REVIEW")
])
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
