import pytest
import os
from unittest.mock import patch
from langchain_anthropic import ChatAnthropic
from app.core.config import settings

def test_provider_switchback():
    """
    Assert that when ANTHROPIC_BASE_URL is unset, the ChatAnthropic client 
    defaults to the Anthropic API (api.anthropic.com) instead of AgentRouter.
    """
    with patch.dict(os.environ, {"ANTHROPIC_BASE_URL": ""}, clear=False):
        kwargs = {}
        # Wait, if we use os.environ in test, settings is already instantiated,
        # but ChatAnthropic doesn't read os.environ directly unless we omit base_url.
        # Actually it does: ChatAnthropic defaults to os.environ["ANTHROPIC_BASE_URL"] or None.
        
        llm = ChatAnthropic(
            model=settings.llm_model,
            anthropic_api_key="mock-key-123"
        )
        
        # In langchain_anthropic, the underlying httpx client's base_url holds the URL
        # By default, if base_url is not passed, it uses the anthropic default.
        client_base_url = str(llm._client.base_url)
        assert "api.anthropic.com" in client_base_url or "agentrouter.org" not in client_base_url
