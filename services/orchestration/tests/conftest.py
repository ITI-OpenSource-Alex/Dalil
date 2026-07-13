import sys
import os
import pytest
# Provide dummy env vars so Pydantic Settings doesn't crash during test collection
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-123")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
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