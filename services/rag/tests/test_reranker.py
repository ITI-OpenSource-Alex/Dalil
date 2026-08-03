"""
services/rag/tests/test_reranker.py

Unit tests for CrossEncoder Re-Ranker component.
"""

from unittest.mock import MagicMock, patch
from app.services.reranker import Reranker


def test_reranker_reordering():
    """Verify candidates are reordered based on cross-encoder logit scores."""
    mock_model = MagicMock()
    # Assume 3 candidates: scores 0.1, 8.5, 3.2 -> candidate at index 1 should move to top
    mock_model.predict.return_value = [0.1, 8.5, 3.2]

    candidates = [
        {"id": "doc1", "content": "chunk 1", "source_url": "http://a.com", "similarity": 0.90},
        {"id": "doc2", "content": "chunk 2", "source_url": "http://b.com", "similarity": 0.70},
        {"id": "doc3", "content": "chunk 3", "source_url": "http://c.com", "similarity": 0.80},
    ]

    with patch("app.services.reranker.get_reranker", return_value=mock_model):
        reranker = Reranker()
        ranked = reranker.rank("test query", candidates, top_n=2)

        assert len(ranked) == 2
        assert ranked[0]["id"] == "doc2"  # Highest score 8.5
        assert ranked[1]["id"] == "doc3"  # Second highest score 3.2


def test_reranker_dict_keys_preserved():
    """Verify every key on every candidate dict survives re-ranking intact."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [5.0]

    candidate = {
        "id": "uuid-123",
        "title": "Sample Title",
        "content": "Sample content body",
        "source_url": "https://example.com/test",
        "similarity": 0.75,
        "relevance_score": 0.75,
        "custom_meta": "extra_val"
    }

    with patch("app.services.reranker.get_reranker", return_value=mock_model):
        reranker = Reranker()
        ranked = reranker.rank("test query", [candidate], top_n=1)

        assert len(ranked) == 1
        res = ranked[0]
        assert res["id"] == "uuid-123"
        assert res["title"] == "Sample Title"
        assert res["content"] == "Sample content body"
        assert res["source_url"] == "https://example.com/test"
        assert res["similarity"] == 0.75
        assert res["relevance_score"] == 0.75
        assert res["custom_meta"] == "extra_val"
        assert "rerank_score" in res


def test_reranker_fallback_on_model_exception():
    """Verify re-ranker degrades gracefully to cosine order on model exception."""
    mock_model = MagicMock()
    mock_model.predict.side_effect = Exception("Model inference timeout")

    candidates = [
        {"id": "doc1", "content": "chunk 1", "similarity": 0.85},
        {"id": "doc2", "content": "chunk 2", "similarity": 0.65},
    ]

    with patch("app.services.reranker.get_reranker", return_value=mock_model):
        reranker = Reranker()
        # Should not raise exception, but fallback to candidate order
        ranked = reranker.rank("test query", candidates, top_n=2)
        assert len(ranked) == 2
        assert ranked[0]["id"] == "doc1"
        assert ranked[1]["id"] == "doc2"
