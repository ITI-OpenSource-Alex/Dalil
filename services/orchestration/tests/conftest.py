import sys
import os
import pytest
# Provide dummy env vars so Pydantic Settings doesn't crash during test collection
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-123")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
os.environ.setdefault("EXAM_SERVICE_URL", "http://exam-test:8085")
# Ensure the orchestration root is in the Python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Enable global async test support
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture(scope="module")
def vcr_config():
    """pytest-recording config for the live-gateway tests (test_agentrouter.py).

    Replay is the default; RUN_LIVE_LLM_TESTS=1 re-records against the real
    gateway. Matching is on method+path only (not full URI or body): CI runs
    with no ANTHROPIC_BASE_URL so the SDK's default host differs from the
    recorded one, and SDK upgrades may reshape the request body — neither
    should invalidate a cassette.
    """
    return {
        # Never persist credentials into committed cassettes.
        "filter_headers": ["authorization", "x-api-key"],
        "match_on": ["method", "path"],
        "record_mode": "all" if os.getenv("RUN_LIVE_LLM_TESTS") == "1" else "none",
    }


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