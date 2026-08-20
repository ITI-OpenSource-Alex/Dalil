import json
import time
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
def mock_redis_deps(mocker):
    mocker.patch("app.services.memory.RedisChatMessageHistory", InMemoryHistory)
    InMemoryHistory._stores.clear()
    # Prevent AsyncRedis connection attempts for exam context caching
    mocker.patch("app.api.chat.fetch_exam_context", return_value=None)
    # Return empty history directly — test_exam_context.py stubs
    # langchain.memory in sys.modules (for isolated runs), which replaces
    # ConversationBufferWindowMemory with a MagicMock when the full suite
    # runs; mocking here keeps the integration tests independent of
    # collection order.
    mocker.patch("app.api.chat.load_memory_variables", return_value={"history": []})

async def test_chat_roundtrip_and_sse_intent(mocker):
    """DoD 3 & 5: evaluate my essay -> Writing service, latency metric recorded"""
    mock_sequence = mocker.MagicMock()
    raw_mock = mocker.MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value={"parsed": IntentResult(intent="WRITING", confidence=0.99), "raw": raw_mock}
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
        
        response = await client.post(
            "/chat",
            json=payload,
            headers={"X-Subscription-Tier": "paid"},
        )
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
            
        assert [event_type for event_type, _ in events] == [
            "status",
            "metadata",
            "status",
            "writing_url",
        ]
        assert events[0][1]["stage"] == "routing"
        assert events[-1][1]["essayId"] == "essay_123"

        # DoD 5: verify downstream latency metric was recorded
        metrics_response = await client.get("/metrics/")
        assert "goa_orchestration_downstream_latency_ms" in metrics_response.text
        assert 'service="writing"' in metrics_response.text

@pytest.mark.parametrize("header_value", ["free", None])
async def test_free_or_missing_tier_rejects_paid_intent_as_sse_error(
    mocker,
    header_value,
):
    mock_sequence = mocker.MagicMock()
    raw_mock = mocker.MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value={
            "parsed": IntentResult(intent="WRITING", confidence=0.99),
            "raw": raw_mock,
        }
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        mock_downstream_client = mocker.MagicMock()
        mock_downstream_client.post = mocker.AsyncMock()
        app.state.http_client = mock_downstream_client
        app.state.langfuse = None

        headers = (
            {"X-Subscription-Tier": header_value}
            if header_value is not None
            else {}
        )
        response = await client.post(
            "/chat",
            headers=headers,
            json={
                "userId": "user_123",
                "sessionId": f"session_free_{header_value}",
                "message": "evaluate my essay",
            },
        )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        assert [event_type for event_type, _ in events] == ["status", "error"]
        assert events[0][1]["stage"] == "routing"
        assert events[-1][1]["error"] == "subscription_required"
        mock_downstream_client.post.assert_not_called()

async def test_free_tier_rag_intent_proceeds(mocker):
    mock_sequence = mocker.MagicMock()
    raw_mock = mocker.MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value={
            "parsed": IntentResult(intent="RAG", confidence=0.95),
            "raw": raw_mock,
        }
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        mock_downstream_client = mocker.MagicMock()
        mock_response = httpx.Response(
            200,
            json={"answer": "RAG answer", "sources": []},
            request=httpx.Request("POST", "http://testserver"),
        )
        mock_downstream_client.post = mocker.AsyncMock(return_value=mock_response)
        app.state.http_client = mock_downstream_client
        app.state.langfuse = None

        response = await client.post(
            "/chat",
            headers={"X-Subscription-Tier": "free"},
            json={
                "userId": "user_123",
                "sessionId": "session_free_rag",
                "message": "What IELTS score do I need?",
            },
        )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        metadata = next(data for kind, data in events if kind == "metadata")
        assert metadata["intent"] == "RAG"
        assert "RAG answer" in "".join(
            data.get("content") or "" for kind, data in events if kind == "token"
        )
        mock_downstream_client.post.assert_called_once()


async def test_explanation_turn_skips_classifier_and_remains_free_tier(mocker):
    classifier = mocker.patch("app.api.chat.classify_intent", new=mocker.AsyncMock())
    explanation = mocker.patch(
        "app.services.client._build_explanation_response",
        new=mocker.AsyncMock(
            return_value="The displayed 82% fit combines the attached profile and requirement factors."
        ),
    )
    mocker.patch("app.api.chat.fetch_user_facts", new=mocker.AsyncMock(return_value=[]))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        downstream = mocker.MagicMock()
        downstream.post = mocker.AsyncMock()
        app.state.http_client = downstream
        app.state.langfuse = None

        response = await client.post(
            "/chat",
            headers={"X-Subscription-Tier": "free"},
            json={
                "userId": "user_explain",
                "sessionId": "session_explain",
                "message": "Why is this programme an 82% fit?",
                "explanationContext": {
                    "kind": "programme_match",
                    "title": "MSc Computer Science 82% fit",
                    "facts": [
                        {"label": "Fit score", "value": "82%"},
                        {"label": "GPA requirement", "value": "3.0"},
                    ],
                    "limitations": ["A fit score is not an admission decision."],
                },
            },
        )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    metadata = next(data for kind, data in events if kind == "metadata")
    assert metadata["intent"] == "GENERAL"
    assert "82% fit" in "".join(
        event[1].get("content") or "" for event in events if event[0] == "token"
    )
    classifier.assert_not_awaited()
    explanation.assert_awaited_once()
    downstream.post.assert_not_called()


async def test_langfuse_failure_does_not_block_chat(mocker):
    mock_sequence = mocker.MagicMock()
    raw_mock = mocker.MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value={
            "parsed": IntentResult(intent="RAG", confidence=0.95),
            "raw": raw_mock,
        }
    )
    mocker.patch("app.services.supervisor.structured_llm", mock_sequence)

    class UnreachableLangfuse:
        def start_observation(self, **_kwargs):
            raise ConnectionError("Langfuse host is unreachable")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        downstream = mocker.MagicMock()
        downstream.post = mocker.AsyncMock(
            return_value=httpx.Response(
                200,
                json={"answer": "RAG answer", "sources": []},
                request=httpx.Request("POST", "http://testserver"),
            )
        )
        app.state.http_client = downstream
        app.state.langfuse = UnreachableLangfuse()

        started = time.perf_counter()
        response = await client.post(
            "/chat",
            json={
                "userId": "user_123",
                "sessionId": "session_unreachable_langfuse",
                "message": "What IELTS score do I need?",
            },
        )
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        metadata = next(data for kind, data in events if kind == "metadata")
        assert metadata["intent"] == "RAG"
        assert elapsed < 1

async def test_downstream_error_circuit_breaker(mocker):
    mock_sequence = mocker.MagicMock()
    raw_mock = mocker.MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_sequence.ainvoke = mocker.AsyncMock(
        return_value={"parsed": IntentResult(intent="RAG", confidence=0.95), "raw": raw_mock}
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

def parse_sse_events(text):
    normalized_text = text.replace("\r\n", "\n")
    events = []
    for block in normalized_text.split("\n\n"):
        if not block.strip():
            continue
        event_type = ""
        event_data = None
        for line in block.strip().split("\n"):
            if line.startswith("event:"):
                event_type = line.replace("event:", "", 1).strip()
            elif line.startswith("data:"):
                event_data = json.loads(line.replace("data:", "", 1).strip())
        if event_data is not None:
            events.append((event_type, event_data))
    return events
