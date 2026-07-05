import sys
import os
import pytest

# Ensure the orchestration root is in the Python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Enable global async test support
pytest_plugins = ["pytest_asyncio"]

@pytest.fixture
def mock_llm(mocker):
    """
    Mock fixture to patch the structured Anthropic invoke call.
    Allows test cases to override intent classification returns.
    """
    from app.services.supervisor import IntentResult
    
    mock_sequence = mocker.MagicMock()
    mock_sequence.ainvoke = mocker.AsyncMock(return_value=IntentResult(intent="WRITING", confidence=0.98))
    
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)
    return mock_sequence.ainvoke