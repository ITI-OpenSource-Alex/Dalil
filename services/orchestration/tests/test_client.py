import pytest
import httpx
from app.services.client import forward_downstream_stream, rag_breaker, writing_breaker
from app.core.metrics import goa_orchestration_circuit_breaker_state





@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Ensure breakers start closed before each test"""
    rag_breaker.close()
    writing_breaker.close()
    goa_orchestration_circuit_breaker_state.labels(service="rag").set(0)
    goa_orchestration_circuit_breaker_state.labels(service="writing").set(0)

@pytest.mark.asyncio
async def test_dod_1_and_7_routing_and_headers(mocker):
    """DoD 1: Correct downstream URL per intent | DoD 7: Headers are propagated"""
    mock_client = mocker.AsyncMock()
    mock_client.post.return_value = httpx.Response(
        200, 
        json={"id": "123", "status": "ok"},
        request=httpx.Request("POST", "http://test")
    )
    gen = forward_downstream_stream(mock_client, "WRITING", "my essay", "user_1", "corr-123")
    events = [e async for e in gen]
    
    mock_client.post.assert_called_once()
    url = mock_client.post.call_args[0][0]
    headers = mock_client.post.call_args[1]["headers"]
    
    assert "writing" in url
    assert "essays" in url
    assert headers["X-Correlation-Id"] == "corr-123"
    assert "X-Internal-Api-Key" in headers
    
    assert events[0].type == "writing_url"
    assert events[0].essayId == "123"

@pytest.mark.asyncio
async def test_dod_2_and_4_circuit_breaker(mocker):
    """DoD 2: Opens after 3 failures | DoD 4: Circuit breaker metric flips to 1"""
    mock_client = mocker.AsyncMock()
    mock_client.post.return_value = httpx.Response(
        200, 
        json={"id": "123", "status": "ok"},
        request=httpx.Request("POST", "http://test")
    )
    mock_client.post.side_effect = httpx.HTTPError("Downstream failed")
    
    assert rag_breaker.current_state == "closed"
    
    # 3 failures trip the breaker
    for _ in range(3):
        gen = forward_downstream_stream(mock_client, "RAG", "hello", "user_1", "corr-1")
        [e async for e in gen]
        
    assert rag_breaker.current_state == "open"
    assert goa_orchestration_circuit_breaker_state.labels(service="rag")._value.get() == 1.0

@pytest.mark.asyncio
async def test_dod_6_timeout_handling(mocker):
    """DoD 6: Timeout throws explicit error message and graceful fallback"""
    mock_client = mocker.AsyncMock()
    mock_client.post.return_value = httpx.Response(
        200, 
        json={"id": "123", "status": "ok"},
        request=httpx.Request("POST", "http://test")
    )
    mock_client.post.side_effect = httpx.ReadTimeout("Request timed out")
    
    gen = forward_downstream_stream(mock_client, "RAG", "msg", "user1", "corr1")
    events = [e async for e in gen]
    
    assert len(events) == 1
    assert events[0].type == "error"
    assert "global opportunity database is currently offline" in events[0].error

@pytest.mark.asyncio
async def test_dod_2_timeout_reset(mocker):
    """DoD 2: Closes after 60s timeout"""
    import datetime
    import pybreaker
    
    mock_client = mocker.AsyncMock()
    mock_client.post.return_value = httpx.Response(
        200, 
        json={"id": "123", "status": "ok"},
        request=httpx.Request("POST", "http://test")
    )
    
    # 1. Open the circuit breaker
    rag_breaker.open()
    assert rag_breaker.current_state == "open"
    
    # 2. Simulate 61 seconds passing by backdating opened_at
    rag_breaker._state_storage.opened_at = datetime.datetime.now(pybreaker.UTC) - datetime.timedelta(seconds=65)
    
    # 3. Call downstream (timeout elapsed -> transitions to half-open -> succeeds -> closes)
    gen = forward_downstream_stream(mock_client, "RAG", "hello", "user_1", "corr-1")
    events = [e async for e in gen]
    
    # 4. Verify the state returned to closed
    assert rag_breaker.current_state == "closed"