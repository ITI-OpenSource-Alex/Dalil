import pytest
from app.services.supervisor import classify_intent, IntentResult

async def test_classify_intent_writing(mock_llm):
    """Verify 'evaluate my essay' is classified as WRITING."""
    mock_llm.return_value = IntentResult(intent="WRITING", confidence=0.98)
    
    result = await classify_intent("evaluate my essay")
    
    assert result.intent == "WRITING"
    assert result.confidence == 0.98
    mock_llm.assert_called_once()

async def test_classify_intent_opportunity(mock_llm):
    """Verify 'find scholarships in Germany' is classified as OPPORTUNITY_SEARCH."""
    mock_llm.return_value = IntentResult(intent="OPPORTUNITY_SEARCH", confidence=0.95)
    
    result = await classify_intent("find scholarships in Germany")
    
    assert result.intent == "OPPORTUNITY_SEARCH"
    assert result.confidence == 0.95
    mock_llm.assert_called_once()

async def test_classify_intent_speaking(mock_llm):
    """Verify 'I want to practice IELTS speaking' is classified as SPEAKING."""
    mock_llm.return_value = IntentResult(intent="SPEAKING", confidence=0.99)
    
    result = await classify_intent("I want to practice IELTS speaking")
    
    assert result.intent == "SPEAKING"
    assert result.confidence == 0.99
    mock_llm.assert_called_once()