import json
import pytest
import httpx
from langchain_core.chat_history import BaseChatMessageHistory
from app.main import app
from app.services.supervisor import IntentResult

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
    """Bypasses physical Redis dependency with an in-memory dictionary store."""
    mocker.patch("app.services.memory.RedisChatMessageHistory", InMemoryHistory)
    InMemoryHistory._stores.clear()

async def test_chat_roundtrip_and_sse_intent(mocker):
    """
    Verify POST /chat returns SSE stream, intent is set in the metadata,
    tokens are forwarded, memory is saved, and metrics/traces are recorded.
    """
    # 1. Mock structured LLM intent classification
    mock_sequence = mocker.MagicMock()
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value=IntentResult(intent="SPEAKING", confidence=0.99)
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    # 2. Request
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Create and mock the downstream client (mock its post method)
        mock_downstream_client = mocker.MagicMock()
        mock_response = httpx.Response(200, json="Practice IELTS speaking.")
        mock_downstream_client.post = mocker.AsyncMock(return_value=mock_response)
        
        # Set app.state.http_client to our mock downstream client
        app.state.http_client = mock_downstream_client
        app.state.langfuse = mocker.MagicMock()  # Mock Langfuse client
        
        payload = {
            "userId": "user_123",
            "sessionId": "session_456",
            "message": "Let's practice speaking"
        }
        
        # Execute chat request (calls the real FastAPI app)
        response = await client.post("/chat", json=payload)
        assert response.status_code == 200
        
        # Parse SSE events separated by double newlines (normalize CRLF)
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
            
        assert len(events) >= 2
        
        # Verify first event is metadata containing intent
        metadata_event = events[0]
        assert metadata_event[0] == "metadata"
        assert metadata_event[1]["type"] == "metadata"
        assert metadata_event[1]["intent"] == "SPEAKING"
        assert metadata_event[1]["confidence"] == 0.99
        
        # Verify tokens are streamed
        token_contents = [ev[1]["content"] for ev in events if ev[0] == "token"]
        assert "".join(token_contents) == "Practice IELTS speaking."

        # Verify Langfuse trace was created
        app.state.langfuse.trace.assert_called_once_with(
            name="chat_request",
            user_id="user_123",
            session_id="session_456",
            metadata=mocker.ANY
        )

        # 4. Verify conversation memory saved both user and assistant response
        history_response = await client.get("/sessions/session_456/history")
        assert history_response.status_code == 200
        history_data = history_response.json()
        
        assert len(history_data) == 2
        assert history_data[0]["role"] == "user"
        assert history_data[0]["content"] == "Let's practice speaking"
        assert history_data[1]["role"] == "assistant"
        assert history_data[1]["content"] == "Practice IELTS speaking."

        # 5. Verify Prometheus metrics updated
        metrics_response = await client.get("/metrics/")
        assert metrics_response.status_code == 200
        metrics_text = metrics_response.text
        assert "goa_orchestration_intent_classified_total" in metrics_text
        assert 'intent="SPEAKING"' in metrics_text

async def test_downstream_error_circuit_breaker(mocker):
    """Verify connection errors in downstream calls correctly yield fallback messages."""
    # 1. Mock structured LLM intent classification to RAG
    mock_sequence = mocker.MagicMock()
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value=IntentResult(intent="RAG", confidence=0.95)
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Create mock downstream client and make it raise HTTPError
        mock_downstream_client = mocker.MagicMock()
        mock_downstream_client.post = mocker.AsyncMock(
            side_effect=httpx.HTTPError("Connection failed to RAG service.")
        )
        
        app.state.http_client = mock_downstream_client
        app.state.langfuse = None
        
        payload = {
            "userId": "user_123",
            "sessionId": "session_error_test",
            "message": "When is the next IELTS exam?"
        }
        
        # Execute chat request (calls the real FastAPI app)
        response = await client.post("/chat", json=payload)
        assert response.status_code == 200
        
        # Parse SSE events
        normalized_text = response.text.replace("\r\n", "\n")
        token_contents = []
        for block in normalized_text.split("\n\n"):
            if not block.strip():
                continue
            lines = block.strip().split("\n")
            for line in lines:
                if line.startswith("data:"):
                    data = json.loads(line.replace("data:", "").strip())
                    if data["type"] == "token":
                        token_contents.append(data["content"])
                        
        response_text = "".join(token_contents)
        assert "global opportunity database is currently offline" in response_text