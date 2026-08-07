"""GOA-045 -- the curated FAQ path, against a real Postgres.

These exercise the actual fuzzy matcher, the real seeded table, the review
window and the admin endpoint. Only the external OpenAI/Anthropic calls are
mocked, so "the LLM was not called" is a genuine assertion about the code path
rather than about a stub.

Run with the compose postgres up:

    docker compose up -d postgres
    DATABASE_URL=postgresql://goa:goa_pass@localhost:5432/rag_db \
    pytest services/rag/tests/test_faq_integration.py -v
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def live_client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_ai_apis(monkeypatch):
    """Mock only the external providers. A FAQ hit must not reach either, and
    that is the point of asserting on the call counts below."""
    mock_embed_response = MagicMock()
    mock_embed_response.data = [MagicMock(embedding=[0.15] * 768)]
    mock_embed = AsyncMock(return_value=mock_embed_response)
    monkeypatch.setattr(
        "app.services.rag_service.embedding_client.embeddings.create", mock_embed
    )

    mock_response = MagicMock()
    mock_response.content = "Mocked LLM answer."
    mock_response.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("app.services.rag_service._invoke_via_sdk", mock_llm)
    return mock_embed, mock_llm


def _run(coro):
    return asyncio.run(coro)


async def _exec(sql, *args):
    conn = await asyncpg.connect(settings.database_url)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


@pytest.fixture
def temp_faq():
    """Inserts a FAQ row and removes it afterwards, so tests never depend on
    (or corrupt) the curated seed set."""
    created = []

    def _insert(question, answer, *, reviewed_at=None, interval_days=365,
                aliases=None, category="test", source_url="https://example.org/policy"):
        row = _run(_exec(
            """
            INSERT INTO faq_entries (question_pattern, answer_markdown, sources,
                                     category, source_url, reviewed_at,
                                     review_interval_days, aliases)
            VALUES ($1, $2, '[]'::jsonb, $3, $4, COALESCE($5, NOW()), $6, $7)
            RETURNING id
            """,
            question, answer, category, source_url, reviewed_at,
            interval_days, aliases or [],
        ))
        created.append(row[0]["id"])
        return row[0]["id"]

    yield _insert

    for faq_id in created:
        _run(_exec("DELETE FROM faq_entries WHERE id = $1", faq_id))


# --------------------------------------------------------------------------
# Matching + threshold
# --------------------------------------------------------------------------

def test_canonical_ielts_question_matches_above_threshold(live_client, mock_ai_apis):
    """GOA-045's headline DoD: 'how do I register for IELTS' matches >0.85.

    This is the case that proved the original matcher used the wrong pg_trgm
    function -- it scored 0.63 under similarity() and could never have hit the
    documented threshold. See docs/faq_threshold_calibration.md.
    """
    _, mock_llm = mock_ai_apis
    res = live_client.post(
        "/query", json={"question": "how do I register for IELTS", "userId": "u1"}
    )
    assert res.status_code == 200
    data = res.json()

    assert "IELTS" in data["answer"]
    assert mock_llm.call_count == 0, "a FAQ hit must not reach the LLM"


def test_faq_hit_skips_embedding_and_retrieval_entirely(live_client, mock_ai_apis):
    """Zero token cost means zero *embedding* cost too.

    Asserting only on the LLM would let a regression that still embeds every
    question pass, which is a real cost on a path whose whole point is being
    free.
    """
    mock_embed, mock_llm = mock_ai_apis
    res = live_client.post(
        "/query", json={"question": "what is a Studienkolleg", "userId": "u1"}
    )
    assert res.status_code == 200
    assert mock_llm.call_count == 0
    assert mock_embed.call_count == 0, "the question was embedded despite a FAQ hit"


def test_faq_answer_carries_a_citation(live_client):
    """A curated answer with no source is indistinguishable from a hallucination.

    GOA-045 requires every entry to store an authoritative source_url; this
    asserts it actually reaches the client rather than just sitting in a column.
    """
    res = live_client.post(
        "/query", json={"question": "what is a Studienkolleg", "userId": "u1"}
    )
    assert res.status_code == 200
    sources = res.json()["sources"]
    assert sources, "FAQ answer returned with no sources"
    assert all(s["source_url"].startswith("http") for s in sources)


def test_alias_matches_a_paraphrase_the_canonical_wording_misses(live_client, mock_ai_apis):
    """'Whats a studienkolleg?' scores 0.769 against the canonical question and
    1.000 via its alias. Aliases are the recall mechanism GOA-045 specifies --
    the alternative, lowering the threshold, buys the same recall by making
    unrelated questions match too."""
    _, mock_llm = mock_ai_apis
    res = live_client.post(
        "/query", json={"question": "Whats a studienkolleg?", "userId": "u1"}
    )
    assert res.status_code == 200
    assert mock_llm.call_count == 0


def test_unrelated_question_does_not_hit_the_faq(live_client, mock_ai_apis):
    """The negative control. A matcher that hits on everything would pass every
    other test in this file.

    Asserted on EMBEDDING, not on the LLM. The FAQ short-circuit returns before
    the question is embedded, so "was it embedded" is exactly "did it take the
    retrieval path". The LLM is a weaker signal: when retrieval finds nothing
    above the confidence threshold, RAG refuses without ever calling it -- so a
    question can correctly bypass the FAQ and still show zero LLM calls.
    """
    mock_embed, _ = mock_ai_apis
    res = live_client.post(
        "/query",
        json={"question": "Tell me about the weather in Cairo", "userId": "u1"},
    )
    assert res.status_code == 200
    assert mock_embed.call_count >= 1, (
        "an unrelated question was served from the curated FAQ"
    )


# --------------------------------------------------------------------------
# Source-sensitive bypass
# --------------------------------------------------------------------------

def test_blocked_account_amount_bypasses_a_near_identical_faq(live_client, mock_ai_apis, temp_faq):
    """The case the whole feature turns on.

    A curated entry about *opening* a blocked account is lexically almost
    identical to a question about *how much* it must contain. One is a stable
    procedure, the other is a figure revised annually. pg_trgm cannot tell them
    apart -- so the question is classified before it is ever matched.
    """
    temp_faq(
        "How do I open a blocked account for the visa?",
        "Curated procedural answer that must NOT be served for an amount question.",
        aliases=["how much money do I need in my blocked account"],
    )

    mock_embed, _ = mock_ai_apis
    res = live_client.post(
        "/query",
        json={
            "question": "How much money do I need in my blocked account?",
            "userId": "u1",
        },
    )
    assert res.status_code == 200
    data = res.json()

    # `answer` is None when retrieval refuses for low confidence, which is still
    # a correct bypass -- the point is that the curated text was not served.
    assert "must NOT be served" not in (data["answer"] or ""), (
        "a source-sensitive question was answered from static text -- even with "
        "an alias engineered to match it exactly"
    )
    assert mock_embed.call_count >= 1, "the volatile question never reached retrieval"


@pytest.mark.parametrize("question", [
    "How much is the German student visa fee?",
    "What is the application deadline for the winter semester?",
    "Am I eligible for a student visa with a 2.5 GPA?",
    "What is the proof of funds requirement?",
    "How long does the APS take?",
])
def test_source_sensitive_questions_always_reach_retrieval(live_client, mock_ai_apis, question):
    mock_embed, _ = mock_ai_apis
    res = live_client.post("/query", json={"question": question, "userId": "u1"})
    assert res.status_code == 200
    assert mock_embed.call_count >= 1, f"{question!r} was served from the FAQ"


# --------------------------------------------------------------------------
# Review window
# --------------------------------------------------------------------------

def test_faq_past_its_review_window_does_not_short_circuit(live_client, mock_ai_apis, temp_faq):
    """An expired entry is still present and still plausible -- it has just aged
    past the point anyone vouched for it. It must not win over live retrieval."""
    marker = f"STALE-{uuid.uuid4().hex[:8]}"
    temp_faq(
        "What is the zzq procedure for expired entries?",
        f"{marker} this answer is out of date",
        reviewed_at=datetime.now(timezone.utc) - timedelta(days=400),
        interval_days=365,
    )

    mock_embed, _ = mock_ai_apis
    res = live_client.post(
        "/query",
        json={"question": "What is the zzq procedure for expired entries?", "userId": "u1"},
    )
    assert res.status_code == 200
    assert marker not in (res.json()["answer"] or ""), "a stale FAQ entry was served"
    assert mock_embed.call_count >= 1, "the query did not fall through to retrieval"


def test_a_fresh_entry_still_wins_when_a_stale_one_is_a_closer_match(
    live_client, mock_ai_apis, temp_faq
):
    """Ordering matters: `ORDER BY sim DESC LIMIT 1` picks one row, so filtering
    staleness AFTER selection would let an expired entry shadow a fresh one and
    return nothing at all."""
    fresh_marker = f"FRESH-{uuid.uuid4().hex[:8]}"
    temp_faq(
        "What is the zzq widget procedure?",
        f"{fresh_marker} current answer",
        reviewed_at=datetime.now(timezone.utc),
    )
    temp_faq(
        "What is the zzq widget procedure exactly?",
        "STALE answer that is a closer lexical match",
        reviewed_at=datetime.now(timezone.utc) - timedelta(days=800),
    )

    _, mock_llm = mock_ai_apis
    res = live_client.post(
        "/query",
        json={"question": "What is the zzq widget procedure?", "userId": "u1"},
    )
    assert res.status_code == 200
    answer = res.json()["answer"]
    assert "STALE" not in answer
    assert fresh_marker in answer, (
        "the fresh entry was shadowed by an expired one that matched more closely"
    )
    assert mock_llm.call_count == 0


# --------------------------------------------------------------------------
# Admin endpoint
# --------------------------------------------------------------------------

def test_admin_endpoint_requires_the_internal_api_key(live_client):
    res = live_client.post("/internal/faq", json={
        "question_pattern": "What is a zzq test entry?",
        "answer_markdown": "answer",
        "source_url": "https://example.org/x",
    })
    assert res.status_code == 401


def test_admin_endpoint_creates_then_updates_by_question(live_client):
    question = f"What is the zzq admin procedure {uuid.uuid4().hex[:6]}?"
    headers = {"X-Internal-API-Key": settings.internal_api_key}
    payload = {
        "question_pattern": question,
        "answer_markdown": "First version.",
        "source_url": "https://example.org/policy",
        "category": "test",
        "sources": [{"source_url": "https://example.org/extra", "title": "Extra"}],
    }
    try:
        created = live_client.post("/internal/faq", json=payload, headers=headers)
        assert created.status_code == 200, created.text
        assert created.json()["created"] is True

        payload["answer_markdown"] = "Second version."
        updated = live_client.post("/internal/faq", json=payload, headers=headers)
        assert updated.status_code == 200
        assert updated.json()["created"] is False, (
            "re-posting the same question inserted a duplicate; two near-identical "
            "entries then compete for the same fuzzy match"
        )
        assert updated.json()["id"] == created.json()["id"]

        rows = _run(_exec(
            "SELECT answer_markdown FROM faq_entries WHERE question_pattern = $1", question
        ))
        assert rows[0]["answer_markdown"] == "Second version."
    finally:
        _run(_exec("DELETE FROM faq_entries WHERE question_pattern = $1", question))


def test_admin_endpoint_refuses_a_source_sensitive_question(live_client):
    """Curating an answer that can never be served is not a harmless no-op: the
    row count reads as coverage while every such question actually goes to
    retrieval."""
    headers = {"X-Internal-API-Key": settings.internal_api_key}
    res = live_client.post("/internal/faq", json={
        "question_pattern": "How much money do I need for the blocked account?",
        "answer_markdown": "11904 EUR",
        "source_url": "https://example.org/policy",
    }, headers=headers)
    assert res.status_code == 422
    assert "source-sensitive" in res.text


def test_admin_endpoint_rejects_a_non_http_source_url(live_client):
    headers = {"X-Internal-API-Key": settings.internal_api_key}
    res = live_client.post("/internal/faq", json={
        "question_pattern": "What is the zzq source url rule?",
        "answer_markdown": "answer",
        "source_url": "not-a-url",
    }, headers=headers)
    assert res.status_code == 422


# --------------------------------------------------------------------------
# Seed integrity
# --------------------------------------------------------------------------

def test_seeded_catalogue_meets_the_acceptance_criteria():
    """30 entries, every one with a citation and a review date.

    Asserting on the shipped data rather than only on behaviour: the AC is about
    coverage, and a schema that permits a sourceless entry would let one back in
    silently.
    """
    rows = _run(_exec(
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE source_url IS NULL OR btrim(source_url) = '') AS no_source,
               count(*) FILTER (WHERE reviewed_at IS NULL) AS no_review,
               count(*) FILTER (WHERE reviewed_at + make_interval(days => review_interval_days) <= NOW()) AS expired
        FROM faq_entries
        WHERE category <> 'test' OR category IS NULL
        """
    ))
    stats = rows[0]
    assert stats["total"] >= 30, f"only {stats['total']} FAQ entries seeded, AC requires 30"
    assert stats["no_source"] == 0
    assert stats["no_review"] == 0
    assert stats["expired"] == 0, (
        "seeded entries are already past their review window -- they will not be "
        "served, so the catalogue is smaller than it looks"
    )


def test_no_seeded_entry_is_itself_source_sensitive():
    """Defence in depth from the other side: the query-path classifier stops a
    volatile *question*, but a volatile *entry* is a curation mistake that the
    classifier would only mask."""
    from app.services.faq_policy import classify_question

    rows = _run(_exec("SELECT question_pattern FROM faq_entries WHERE category <> 'test'"))
    offenders = [
        r["question_pattern"] for r in rows
        if not classify_question(r["question_pattern"]).allowed
    ]
    assert not offenders, (
        "these curated entries ask source-sensitive questions and can never be "
        f"served: {offenders}"
    )


# --------------------------------------------------------------------------
# Near-miss guard
# --------------------------------------------------------------------------

def test_a_question_about_another_country_does_not_match_the_germany_entry(
    live_client, mock_ai_apis
):
    """The false positive that set the threshold.

    word_similarity() scores the best CONTIGUOUS EXTENT of the pattern, so a
    question sharing a long prefix scores high even when the one word that
    changes the answer differs. This pair scores 0.862 -- above the 0.85 the
    ticket documents -- and would have answered a question about France with
    German requirements, citing a German source.

    The entries most exposed are the ones users can least afford to get wrong:
    country names, IELTS Academic vs General, public vs private insurance.
    """
    mock_embed, _ = mock_ai_apis
    res = live_client.post("/query", json={
        "question": (
            "Is the Egyptian Thanaweya Amma certificate recognized for "
            "university admission in France?"
        ),
        "userId": "u1",
    })
    assert res.status_code == 200
    answer = res.json()["answer"] or ""

    assert "Abitur" not in answer, (
        "a question about France was answered from the Germany entry"
    )
    assert mock_embed.call_count >= 1, "the near-miss short-circuited instead of retrieving"


def test_threshold_is_above_the_measured_near_miss():
    """Pins the constant to the evidence rather than to a docstring.

    0.862 is the measured score of the France/Germany near-miss. A future edit
    that lowers the threshold back toward the originally documented 0.85 would
    silently reintroduce that answer, and no behavioural test would obviously
    fail if the seed data happened to change.
    """
    from app.services.rag_service import FAQ_SIMILARITY_THRESHOLD

    assert FAQ_SIMILARITY_THRESHOLD > 0.862, (
        "threshold sits at or below the measured France/Germany near-miss; see "
        "docs/faq_threshold_calibration.md"
    )
