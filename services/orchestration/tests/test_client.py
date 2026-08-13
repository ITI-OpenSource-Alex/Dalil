import pytest
import httpx
from app.services.client import (
    _build_explanation_response,
    forward_downstream_stream,
    rag_breaker,
    writing_breaker,
)
from app.core.metrics import goa_orchestration_circuit_breaker_state





@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Ensure breakers start closed before each test"""
    rag_breaker.close()
    writing_breaker.close()
    goa_orchestration_circuit_breaker_state.labels(service="rag").set(0)
    goa_orchestration_circuit_breaker_state.labels(service="writing").set(0)

@pytest.mark.asyncio
@pytest.mark.parametrize("intent, expected_url, expected_event_type", [
    ("WRITING", "writing_service_url/essays", "writing_url"),
    ("RAG", "rag_service_url/query", "token"),
    ("OPPORTUNITY_SEARCH", "rag_service_url/match", "match_results"),
    ("CV_REVIEW", "writing_service_url/essays", "token"),
])
async def test_dod_1_and_7_routing_and_headers(mocker, intent, expected_url, expected_event_type):
    """DoD 1: Correct downstream URL per intent | DoD 7: Headers are propagated"""
    mock_client = mocker.AsyncMock()
    
    # RAG/CV_REVIEW expect sources as well
    mock_client.post.return_value = httpx.Response(
        200, 
        json={"id": "123", "status": "ok", "answer": "12345", "sources": ["source1"]},
        request=httpx.Request("POST", "http://test")
    )
    
    gen = forward_downstream_stream(mock_client, intent, "my message", "user_1", "corr-123", ["attachment.txt"])
    events = [e async for e in gen]
    
    mock_client.post.assert_called()
    # First call url
    url = mock_client.post.call_args_list[0][0][0]
    headers = mock_client.post.call_args_list[0][1]["headers"]
    
    # Basic URL check based on intent
    if intent == "WRITING" or intent == "CV_REVIEW":
        assert "writing" in url
    else:
        assert "rag" in url
        
    assert headers["X-Correlation-Id"] == "corr-123"
    assert "X-Internal-Api-Key" in headers
    
    assert events[0].type == expected_event_type


@pytest.mark.asyncio
async def test_speaking_intent_routing(mocker):
    """DoD 1: Speaking intent correctly routes to WS URL without calling client"""
    mock_client = mocker.AsyncMock()
    gen = forward_downstream_stream(mock_client, "SPEAKING", "my message", "user_1", "corr-123")
    events = [e async for e in gen]
    
    mock_client.post.assert_not_called()
    assert len(events) == 1
    assert events[0].type == "speaking_url"
    assert "ws" in events[0].wsUrl


@pytest.mark.asyncio
async def test_explanation_context_bypasses_downstream_services(mocker):
    mock_client = mocker.AsyncMock()
    explanation = mocker.patch(
        "app.services.client._build_explanation_response",
        new=mocker.AsyncMock(return_value="Your score is based on the attached criteria."),
    )
    context = {
        "kind": "speaking_score",
        "title": "your speaking band 6.5",
        "facts": [{"label": "Fluency", "value": "6.0"}],
        "limitations": ["Practice estimate only"],
    }

    events = [
        event
        async for event in forward_downstream_stream(
            mock_client,
            "GENERAL",
            "Why did I get this score?",
            "user_1",
            "corr-explain",
            explanation_context=context,
        )
    ]

    explanation.assert_awaited_once_with("Why did I get this score?", context)
    mock_client.post.assert_not_called()
    assert "".join(event.content or "" for event in events) == (
        "Your score is based on the attached criteria."
    )
    assert all(event.type == "token" for event in events)


@pytest.mark.asyncio
async def test_explanation_extracts_text_after_agentrouter_thinking_blocks(mocker):
    response = mocker.MagicMock()
    response.content = [
        {"type": "thinking", "thinking": ""},
        {"type": "tool_use", "name": "internal"},
        {"type": "text", "text": "The 100% is the displayed fit score."},
    ]
    llm_mock = mocker.MagicMock()
    llm_mock.ainvoke = mocker.AsyncMock(return_value=response)
    mocker.patch("app.services.client.llm", llm_mock)

    answer = await _build_explanation_response(
        "Why is this 100% fit?",
        {
            "kind": "programme_match",
            "title": "Computer Science fit result",
            "facts": [{"label": "Fit score", "value": "100%"}],
        },
    )

    assert answer == "The 100% is the displayed fit score."
    llm_mock.ainvoke.assert_awaited_once()
    messages = llm_mock.ainvoke.await_args.args[0]
    assert "Fit score" in messages[1].content


@pytest.mark.asyncio
async def test_programme_explanation_is_deterministic_and_actionable(mocker):
    llm_mock = mocker.MagicMock()
    llm_mock.ainvoke = mocker.AsyncMock()
    mocker.patch("app.services.client.llm", llm_mock)

    answer = await _build_explanation_response(
        "Why is Computer Science shown as 100% fit?",
        {
            "kind": "programme_match",
            "title": "Computer Science fit result",
            "facts": [
                {"label": "Fit score", "value": "100%"},
                {"label": "Eligibility points", "value": "40"},
                {"label": "Requirement headroom points", "value": "15"},
                {"label": "Subject fit points", "value": "35"},
                {"label": "Destination fit points", "value": "10"},
                {"label": "Published requirements met", "value": "3"},
                {"label": "Published requirements evaluated", "value": "3"},
                {"label": "Application deadline", "value": "No published deadline"},
            ],
            "limitations": [
                "The fit score depends on the profile information currently saved in Dalil."
            ],
        },
    )

    assert "40" in answer
    assert "15" in answer
    assert "35" in answer
    assert "10" in answer
    assert "3 of 3" in answer
    assert "no score gap" in answer
    assert "verify the application deadline" in answer.lower()
    assert "not an admission decision" in answer
    llm_mock.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_thinking_only_response_falls_back_to_attached_evidence(mocker):
    response = mocker.MagicMock()
    response.content = [{"type": "thinking", "thinking": "internal"}]
    llm_mock = mocker.MagicMock()
    llm_mock.ainvoke = mocker.AsyncMock(return_value=response)
    mocker.patch("app.services.client.llm", llm_mock)

    answer = await _build_explanation_response(
        "Why did I receive this band?",
        {
            "kind": "writing_score",
            "title": "Writing score",
            "facts": [{"label": "Grammar band", "value": "6.0"}],
            "limitations": ["This is a practice estimate."],
        },
    )

    assert "Grammar band: **6.0**" in answer
    assert "This is a practice estimate." in answer
    assert "couldn't produce" not in answer


@pytest.mark.asyncio
async def test_traceparent_is_forwarded_to_rag(mocker):
    mock_client = mocker.AsyncMock()
    mock_client.post.return_value = httpx.Response(
        200,
        json={"answer": "ok", "sources": []},
        request=httpx.Request("POST", "http://test"),
    )
    traceparent = f"00-{'a' * 32}-{'b' * 16}-01"

    events = [
        event
        async for event in forward_downstream_stream(
            mock_client,
            "RAG",
            "hello",
            "user_1",
            "corr-123",
            traceparent=traceparent,
        )
    ]

    assert events
    assert mock_client.post.call_args.kwargs["headers"]["traceparent"] == traceparent


@pytest.mark.asyncio
@pytest.mark.parametrize("intent,event_type,url_field", [
    ("SPEAKING", "speaking_url", "wsUrl"),
    ("WRITING", "writing_url", "sseUrl"),
])
async def test_browser_handoff_urls_carry_traceparent(
    mocker,
    intent,
    event_type,
    url_field,
):
    mock_client = mocker.AsyncMock()
    mock_client.post.return_value = httpx.Response(
        200,
        json={"id": "123", "status": "ready"},
        request=httpx.Request("POST", "http://test"),
    )
    traceparent = f"00-{'c' * 32}-{'d' * 16}-01"

    events = [
        event
        async for event in forward_downstream_stream(
            mock_client,
            intent,
            "hello",
            "user_1",
            "corr-123",
            traceparent=traceparent,
        )
    ]

    handoff = next(event for event in events if event.type == event_type)
    assert f"traceparent={traceparent}" in getattr(handoff, url_field)

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
    _events = [e async for e in gen]  # drained for side effects
    
    # 4. Verify the state returned to closed
    assert rag_breaker.current_state == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_logging(mocker, capsys):
    """Verify correlation_id on open and downtime_s on close"""
    mock_client = mocker.AsyncMock()
    mock_client.post.side_effect = httpx.HTTPError("Downstream failed")
    
    # Clear any previous output
    capsys.readouterr()
    
    # Open the breaker
    for _ in range(3):
        gen = forward_downstream_stream(mock_client, "RAG", "hello", "user", "corr-log-123")
        [e async for e in gen]
        
    out, err = capsys.readouterr()
    assert "Circuit breaker opened" in out
    assert "corr-log-123" in out
    
    # Reset and mock a successful call to close it
    mock_client.post.side_effect = None
    mock_client.post.return_value = httpx.Response(200, json={"id": "123", "status": "ok", "answer": "1", "sources": []}, request=httpx.Request("POST", "http://test"))
    
    import pybreaker
    import datetime
    from app.services.client import rag_breaker
    rag_breaker._state_storage.opened_at = datetime.datetime.now(pybreaker.UTC) - datetime.timedelta(seconds=65)
    
    gen = forward_downstream_stream(mock_client, "RAG", "hello", "user", "corr-log-123")
    [e async for e in gen]
    
    out, err = capsys.readouterr()
    assert "Circuit breaker closed" in out
    assert "downtime_s" in out


@pytest.mark.asyncio
async def test_circuit_breaker_ignores_4xx(mocker):
    """Verify HTTPStatusError < 500 is raised without tripping the breaker"""
    mock_client = mocker.AsyncMock()
    # Mock a 400 Bad Request error
    resp = httpx.Response(400, request=httpx.Request("POST", "http://test"))
    mock_client.post.side_effect = httpx.HTTPStatusError("Bad Request", request=resp.request, response=resp)
    
    assert rag_breaker.current_state == "closed"
    
    # Run 5 times (normally 3 failures trip the breaker)
    for _ in range(5):
        gen = forward_downstream_stream(mock_client, "RAG", "hello", "user_1", "corr-1")
        # Generator handles the exception and converts to an error event
        events = [e async for e in gen]
        assert len(events) == 1
        assert events[0].type == "error"
        assert "global opportunity database is currently offline" in events[0].error
        
    # The circuit breaker MUST remain closed because 400 is not a system error
    assert rag_breaker.current_state == "closed"
