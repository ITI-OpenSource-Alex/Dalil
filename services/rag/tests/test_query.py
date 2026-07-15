import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.rag_service import generate_embedding, query_rag

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_external_apis(monkeypatch):
    """Mock external OpenAI and Anthropic API calls at class level to bypass Pydantic validations."""
    # 1. Mock OpenAI embeddings class method
    mock_embed = AsyncMock(return_value=[0.15] * 1536)
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings.aembed_query", mock_embed)

    # 2. Mock Anthropic LLM Chat class method
    mock_response = MagicMock()
    mock_response.content = "Based on the context, students need a valid passport."
    mock_response.response_metadata = {
        "usage": {"input_tokens": 45, "output_tokens": 12}
    }
    mock_llm = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic.ainvoke", mock_llm)

    return mock_embed, mock_llm


def make_mock_db_pool(monkeypatch, similarity_score=0.85):
    """Helper to instantiate mock database connection returning a specified similarity score."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    # Mock the returned records from connection fetch
    mock_row = {
        "id": "d3b07384-d113-4956-a574-0f2c0032e52e",
        "content": "Visa requirement chunk details for study visa.",
        "source_url": "https://visa-info.com/student",
        "similarity": similarity_score,
    }
    mock_conn.fetch = AsyncMock(return_value=[mock_row])

    # Create the context manager mock
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    # Calling pool.acquire() returns the context manager
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    monkeypatch.setattr("app.core.database.db.pool", mock_pool)
    return mock_pool, mock_conn


@pytest.fixture
def mock_db_pool(monkeypatch):
    """Fixture for standard high-similarity db pool setup."""
    pool, conn = make_mock_db_pool(monkeypatch, similarity_score=0.85)
    return pool, conn


@pytest.fixture
def mock_langfuse(monkeypatch):
    """Fixture to mock and inject Langfuse client for verification."""
    mock_lf = MagicMock()
    mock_trace = MagicMock()
    mock_lf.trace.return_value = mock_trace

    monkeypatch.setattr("app.services.rag_service.langfuse_client", mock_lf)
    return mock_lf, mock_trace


def get_prometheus_counter_value(metrics_text: str, counter_name: str) -> float:
    """Helper to parse a counter's float value from Prometheus text output."""
    for line in metrics_text.splitlines():
        if line.startswith(counter_name) and not line.startswith("#"):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[1])
    return 0.0


@pytest.mark.asyncio
async def test_generate_embedding():
    """Verify generate_embedding returns a 1536-dimensional vector."""
    vector = await generate_embedding("test question")
    assert isinstance(vector, list)
    assert len(vector) == 1536
    assert vector[0] == 0.15


@pytest.mark.asyncio
async def test_query_rag(mock_db_pool):
    """Verify RAG service coordinates embeddings, similarity queries, and LLM calls."""
    answer, sources, metrics = await query_rag(
        question="How to get a student visa?", user_id="test-user-123", top_k=3
    )

    assert "passport" in answer
    assert len(sources) == 1
    assert sources[0]["similarity"] == 0.85
    assert metrics["question_hash"] is not None
    assert metrics["chunks_retrieved"] == 1
    assert metrics["answer_tokens"] == 12


def test_api_query_endpoint(mock_db_pool, monkeypatch):
    """Verify endpoint HTTP request validation, correlation headers, and response structure."""
    payload = {"question": "What are the visa rules?", "userId": "user-456", "topK": 2}

    response = client.post(
        "/query", json=payload, headers={"X-Correlation-Id": "test-correlation-xyz"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["similarity"] == 0.85


def test_api_query_langfuse_tracing(mock_db_pool, mock_langfuse):
    """Verify that POST /query initiates a Langfuse trace with retrieval and generation spans."""
    mock_lf, mock_trace = mock_langfuse
    payload = {"question": "Traced question rules?", "userId": "user-789", "topK": 3}

    response = client.post("/query", json=payload)
    assert response.status_code == 200

    # Ensure the parent trace was initiated
    mock_lf.trace.assert_called_once()
    # Ensure retrieval span and generation components were called
    mock_trace.span.assert_called_once()
    mock_trace.generation.assert_called_once()


def test_low_similarity_increments_metrics_counter(monkeypatch):
    """Verify that submitting a low-similarity query increments the low-confidence metric."""
    # 1. Mock DB pool to return low similarity score (0.50, which is < 0.60 threshold)
    make_mock_db_pool(monkeypatch, similarity_score=0.50)

    # 2. Get counter value before execution
    metrics_before = client.get("/metrics").text
    val_before = get_prometheus_counter_value(
        metrics_before, "goa_rag_low_confidence_total"
    )

    # 3. Run low similarity query
    payload = {
        "question": "Irrelevant text that matches poorly",
        "userId": "user-999",
        "topK": 1,
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 200

    # 4. Check counter value after execution
    metrics_after = client.get("/metrics").text
    val_after = get_prometheus_counter_value(
        metrics_after, "goa_rag_low_confidence_total"
    )

    # Confirm it has incremented by exactly 1.0
    assert val_after == val_before + 1.0


def test_api_visa_requirements_endpoint(monkeypatch):
    """Verify the authenticated internal visa route validates schema and returns 200 OK.

    Auth (Task 04) and the real insert/update/unchanged upsert behavior (Task 03) have
    dedicated, more thorough coverage in test_visa.py; this test only guards that the
    route wiring itself (schema + auth + service call) still returns success end-to-end.
    """
    payload = {
        "country": "Germany",
        "visa_type": "Student",
        "issuing_body": "German Embassy",
        "requirements": {"passport": True, "funds_eur": 11208},
        "proof_of_funds": {"blocked_account": True},
        "source_url": "https://germany.info",
        "processing_days_min": 30,
        "processing_days_max": 90,
        "notes": "Bring physical biometric photos.",
        "content_hash": "abc123hash",
        "egyptian_specific": True
    }

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": "11111111-1111-1111-1111-111111111111", "inserted": True})
    mock_tx_ctx = MagicMock()
    mock_tx_ctx.__aenter__ = AsyncMock(return_value=None)
    mock_tx_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx_ctx)
    mock_pool_ctx = MagicMock()
    mock_pool_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_pool_ctx)
    monkeypatch.setattr("app.core.database.db.pool", mock_pool)

    response = client.post(
        "/internal/visa-requirements",
        json=payload,
        headers={"X-Internal-Api-Key": settings.internal_api_key}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_health_check_endpoint():
    """Verify standard health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
