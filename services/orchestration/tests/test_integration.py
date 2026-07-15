import json
import pytest
import httpx
from langchain_core.chat_history import BaseChatMessageHistory
from app.main import app
from app.services.supervisor import IntentResult
from app.core.metrics import goa_orchestration_downstream_latency_ms

class InMemoryHistory(BaseChatMessageHistory):
    _stores = {}
    def __init__(self, session_id, redis_url=None, ttl=None, **kwargs):
        self.session_id = session_id
        if session_id not in self._stores:
            self._stores[session_id] = []
    @property
    def messages(self):
        return self._stores[self.session_id]
    def add_messages(self, messages):
        self._stores[self.session_id].extend(messages)
    def add_message(self, message):
        self._stores[self.session_id].append(message)
    def clear(self):
        self._stores[self.session_id] = []

@pytest.fixture(autouse=True)
def mock_redis_history(mocker):
    mocker.patch("app.services.memory.RedisChatMessageHistory", InMemoryHistory)
    InMemoryHistory._stores.clear()

async def test_chat_roundtrip_and_sse_intent(mocker):
    """DoD 3 & 5: evaluate my essay -> Writing service, latency metric recorded"""
    mock_sequence = mocker.MagicMock()
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value=IntentResult(intent="WRITING", confidence=0.99)
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        mock_downstream_client = mocker.MagicMock()
        mock_response = httpx.Response(
            200, 
            json={"id": "essay_123", "status": "ready"},
            request=httpx.Request("POST", "http://testserver")
        )
        mock_downstream_client.post = mocker.AsyncMock(return_value=mock_response)
        
        app.state.http_client = mock_downstream_client
        app.state.langfuse = mocker.MagicMock()
        
        payload = {
            "userId": "user_123",
            "sessionId": "session_456",
            "message": "evaluate my essay"
        }
        
        response = await client.post("/chat", json=payload)
        assert response.status_code == 200
        
        # Verify Writing Service was called
        mock_downstream_client.post.assert_called_once()
        url = mock_downstream_client.post.call_args[0][0]
        assert "writing" in url
        
        normalized_text = response.text.replace("\r\n", "\n")
        events = []
        for block in normalized_text.split("\n\n"):
            if not block.strip():
                continue
            lines = block.strip().split("\n")
            event_type = ""
            event_data = {}
            for line in lines:
                if line.startswith("event:"):
                    event_type = line.replace("event:", "").strip()
                elif line.startswith("data:"):
                    event_data = json.loads(line.replace("data:", "").strip())
            if event_data:
                events.append((event_type, event_data))
            
        assert len(events) == 2
        assert events[0][0] == "metadata"
        assert events[1][0] == "writing_url"
        assert events[1][1]["essayId"] == "essay_123"

        # DoD 5: verify downstream latency metric was recorded
        metrics_response = await client.get("/metrics/")
        assert "goa_orchestration_downstream_latency_ms" in metrics_response.text
        assert 'service="writing"' in metrics_response.text

async def test_downstream_error_circuit_breaker(mocker):
    mock_sequence = mocker.MagicMock()
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value=IntentResult(intent="RAG", confidence=0.95)
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        mock_downstream_client = mocker.MagicMock()
        mock_downstream_client.post = mocker.AsyncMock(
            side_effect=httpx.HTTPError("Connection failed")
        )
        app.state.http_client = mock_downstream_client
        app.state.langfuse = None
        
        response = await client.post("/chat", json={
            "userId": "user_123",
            "sessionId": "session_error_test",
            "message": "When is the next IELTS exam?"
        })
        
        normalized_text = response.text.replace("\r\n", "\n")
        error_found = False
        for block in normalized_text.split("\n\n"):
            if "database is currently offline" in block:
                error_found = True
                
        assert error_found