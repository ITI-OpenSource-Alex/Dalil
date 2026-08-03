"""
services/rag/tests/test_citations.py

Unit tests for Citation Schema and DocumentSource title metadata handling.
"""

from app.schemas.query import DocumentSource, QueryResponse


def test_document_source_null_title_handling():
    """Verify DocumentSource correctly accepts title=None without synthesizing artificial strings."""
    doc = DocumentSource(
        id="uuid-abc",
        title=None,
        source_url="https://www.mastersportal.com/studies/123",
        content="Program details content",
        similarity=0.72
    )

    assert doc.id == "uuid-abc"
    assert doc.title is None
    assert doc.url == "https://www.mastersportal.com/studies/123"
    assert doc.relevance_score == 0.72


def test_document_source_populated_title():
    """Verify DocumentSource preserves populated stored title metadata."""
    doc = DocumentSource(
        id="uuid-xyz",
        title="Official IELTS Band Descriptors Guide",
        source_url="https://ielts.org/scoring",
        content="Band 7 means Good User...",
        similarity=0.88
    )

    assert doc.title == "Official IELTS Band Descriptors Guide"
    assert doc.url == "https://ielts.org/scoring"
    assert doc.relevance_score == 0.88


def test_query_response_refusal_schema():
    """Verify QueryResponse accepts answer=None alongside refusal reason and suggestions."""
    resp = QueryResponse(
        answer=None,
        reason="insufficient_data",
        suggestion="Please rephrase with more details.",
        sources=[
            DocumentSource(
                id="doc-1",
                title=None,
                source_url="https://example.com",
                content="weak chunk",
                similarity=0.42
            )
        ]
    )

    assert resp.answer is None
    assert resp.reason == "insufficient_data"
    assert resp.suggestion == "Please rephrase with more details."
    assert len(resp.sources) == 1
    assert resp.sources[0].relevance_score == 0.42
