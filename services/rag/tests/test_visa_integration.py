"""
GOA-086 Task 18 -- integration tests for the visa requirements feature.

Unlike the unit tests in test_visa.py / test_query.py (which mock app.core.database.db
entirely), these tests require a REAL, live Postgres connection and exercise the actual
database: real schema, real cosine-similarity retrieval, real upsert logic. Only the
external OpenAI/Anthropic API calls are mocked, since no real API keys are configured
for this project (matching the existing mocking approach in test_query.py).

Run with the docker-compose postgres (and redis-cache) services up, e.g.:

    docker compose up -d postgres redis-cache
    DATABASE_URL=postgresql://goa:goa_pass@localhost:5432/rag_db \
    pytest services/rag/tests/test_visa_integration.py -v

Each test inserts its own fixture rows and cleans them up afterward, leaving the
database in the state it found it.
"""
import asyncio
import uuid

import asyncpg
import pytest
from pgvector.asyncpg import register_vector
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

@pytest.fixture
def live_client():
    """
    A TestClient used as a context manager triggers the app's real lifespan startup
    (db.connect() / db.disconnect()), giving request handlers a real, connected
    app.core.database.db.pool for the duration of the block -- required since
    query_rag() and upsert_visa_requirements() both call db.pool.acquire() directly.
    app.core.database.py registers pgvector's asyncpg codec on this pool, so real
    Python lists can be passed directly as $N::vector parameters.
    """
    with TestClient(app) as c:
        yield c


FIXED_EMBEDDING = [0.15] * 768
UNRELATED_EMBEDDING = [-0.15] * 768


@pytest.fixture(autouse=True)
def mock_ai_apis(monkeypatch):
    """Mock only the external OpenAI/Anthropic calls -- no real API keys are configured
    for this project. Retrieval itself still hits the real, live Postgres."""
    mock_embed_response = MagicMock()
    mock_embed_response.data = [MagicMock(embedding=[0.15] * 768)]
    mock_embed = AsyncMock(return_value=mock_embed_response)
    monkeypatch.setattr("app.services.rag_service.embedding_client.embeddings.create", mock_embed)

    mock_response = MagicMock()
    mock_response.content = "Mocked answer."
    mock_response.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    mock_llm = AsyncMock(return_value=mock_response)
    # RAG generation calls the Anthropic SDK directly rather than going through
    # ChatAnthropic.ainvoke: langchain_anthropic 0.1.13 reads content[0].text and
    # blows up on thinking blocks. Patch the seam that is actually used.
    monkeypatch.setattr("app.services.rag_service._invoke_via_sdk", mock_llm)
    return mock_embed, mock_llm


def _run(coro):
    """Runs a one-off coroutine against a fresh connection/event loop, independent of
    whatever event loop TestClient uses internally for the app's own db.pool -- avoids
    binding an asyncpg connection to the wrong loop."""
    return asyncio.run(coro)


async def _connect():
    """A standalone connection (independent of app.core.database.db.pool) with
    pgvector's codec registered, so vector columns can be written/read as plain
    Python lists here too."""
    conn = await asyncpg.connect(dsn=settings.database_url)
    await register_vector(conn)
    return conn


async def _insert_document(doc_id, source_url, category, content, embedding):
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO documents (id, content, embedding, source_url, category, last_updated) "
            "VALUES ($1, $2, $3::vector, $4, $5, NOW())",
            doc_id, content, embedding, source_url, category,
        )
    finally:
        await conn.close()


async def _delete_documents(doc_ids):
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        await conn.execute("DELETE FROM documents WHERE id = ANY($1::uuid[])", doc_ids)
    finally:
        await conn.close()


async def _fetch_visa_requirement(row_id):
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        return await conn.fetchrow(
            "SELECT country, visa_type, issuing_body, egyptian_specific, last_scraped_at "
            "FROM visa_requirements WHERE id = $1",
            row_id,
        )
    finally:
        await conn.close()


async def _count_visa_requirements(country, visa_type, issuing_body):
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM visa_requirements "
            "WHERE country = $1 AND visa_type = $2 AND issuing_body = $3",
            country, visa_type, issuing_body,
        )
    finally:
        await conn.close()


async def _delete_visa_requirement(country, visa_type, issuing_body):
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        await conn.execute(
            "DELETE FROM visa_requirements WHERE country = $1 AND visa_type = $2 AND issuing_body = $3",
            country, visa_type, issuing_body,
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# POST /internal/visa-requirements through the real route + real database
# (exercises Tasks 02/03/04 together, not just their individual unit tests)
# ---------------------------------------------------------------------------

def test_visa_requirements_endpoint_persists_via_real_http_and_real_db(live_client):
    payload = {
        "country": "Germany",
        "visa_type": "Student Visa (Task 18 Integration Test)",
        "issuing_body": "GOA-086 Task 18 Integration Test",
        "requirements": {"items": ["Valid passport"]},
        "proof_of_funds": {"amount_eur": 11208.0},
        "source_url": "https://kairo.diplo.de/integration-test",
        "processing_days_min": 15,
        "processing_days_max": 20,
        "notes": None,
        "content_hash": "task18-integration-hash",
        "egyptian_specific": True,
    }

    try:
        response = live_client.post(
            "/internal/visa-requirements",
            json=payload,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["action"] == "inserted"

        row = _run(_fetch_visa_requirement(uuid.UUID(data["id"])))
        assert row is not None
        assert row["country"] == "Germany"
        assert row["issuing_body"] == "GOA-086 Task 18 Integration Test"
        assert row["egyptian_specific"] is True
    finally:
        _run(_delete_visa_requirement(
            payload["country"], payload["visa_type"], payload["issuing_body"]
        ))


def test_visa_requirements_endpoint_is_idempotent_for_identical_resubmission(live_client):
    """Submitting the exact same payload twice must not create a duplicate row, and
    must leave last_scraped_at unchanged (the whole point of content_hash-aware
    skipping is to avoid needless churn when nothing actually changed)."""
    payload = {
        "country": "Germany",
        "visa_type": "Student Visa (Idempotency Test)",
        "issuing_body": "GOA-086 Idempotency Test",
        "requirements": {"items": ["Valid passport"]},
        "proof_of_funds": {"amount_eur": 11208.0},
        "source_url": "https://kairo.diplo.de/idempotency-test",
        "processing_days_min": 15,
        "processing_days_max": 20,
        "notes": None,
        "content_hash": "identical-content-hash",
        "egyptian_specific": True,
    }

    try:
        first = live_client.post(
            "/internal/visa-requirements", json=payload,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        )
        assert first.status_code == 200
        first_data = first.json()
        assert first_data["action"] == "inserted"

        row_after_first = _run(_fetch_visa_requirement(uuid.UUID(first_data["id"])))
        last_scraped_at_after_first = row_after_first["last_scraped_at"]

        # Resubmit the exact same payload.
        second = live_client.post(
            "/internal/visa-requirements", json=payload,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        )
        assert second.status_code == 200
        second_data = second.json()
        assert second_data["action"] == "unchanged"
        assert second_data["id"] == first_data["id"]

        # No duplicate row: exactly one row for this key.
        count = _run(_count_visa_requirements(
            payload["country"], payload["visa_type"], payload["issuing_body"]
        ))
        assert count == 1

        row_after_second = _run(_fetch_visa_requirement(uuid.UUID(second_data["id"])))
        assert row_after_second["last_scraped_at"] == last_scraped_at_after_first
    finally:
        _run(_delete_visa_requirement(
            payload["country"], payload["visa_type"], payload["issuing_body"]
        ))


# ---------------------------------------------------------------------------
# /query against real, live-retrieved content
# ---------------------------------------------------------------------------

def test_query_answers_aps_certificate_question_from_real_retrieval(live_client, mock_ai_apis):
    """
    NOTE on source domains: the Definition of Done's example expects a citation of
    "cairo.diplo.de" or "aps-egypt.de". This project's actual GermanEmbassyCairoAdapter
    / APSCairoAdapter are configured against "kairo.diplo.de" (the German missions'
    real <city>.diplo.de convention -- Kairo is the German spelling) and
    "aps-cairo.org" -- neither exact domain was ever confirmed by live browsing (both
    plans explicitly flag the exact source URL as an open item). Rather than swap in
    the DoD's suggested domains on no better evidence, this test asserts a citation of
    the adapter's actual configured domain, which is the substantively correct thing
    to verify (that retrieval genuinely finds and cites the APS Cairo source).
    """
    _, mock_llm = mock_ai_apis
    aps_id = uuid.uuid4()
    distractor_id = uuid.uuid4()
    aps_source_url = "https://www.aps-cairo.org/procedure-task18-test"

    try:
        _run(_insert_document(
            aps_id, aps_source_url, "visa",
            "APS Cairo issues the APS certificate required for German student visa "
            "applications from Egypt, verifying the authenticity of academic certificates.",
            FIXED_EMBEDDING,
        ))
        _run(_insert_document(
            distractor_id, "https://example.com/unrelated", "scholarships",
            "Chevening scholarships are fully funded by the UK government.",
            UNRELATED_EMBEDDING,
        ))

        response = live_client.post("/query", json={
            "question": "Do I need an APS certificate for Germany?",
            "userId": "task18-integration-test-user",
            "topK": 3,
        })

        assert response.status_code == 200
        data = response.json()

        # The prompt actually sent to the LLM must contain the genuinely-retrieved
        # APS content -- this is the real signal that live retrieval worked, since the
        # LLM call itself is mocked.
        prompt_sent_to_llm = mock_llm.call_args[0][0]
        assert "APS certificate" in prompt_sent_to_llm

        # The response must cite the APS document's source_url.
        cited_urls = {s["source_url"] for s in data["sources"]}
        assert aps_source_url in cited_urls
    finally:
        _run(_delete_documents([aps_id, distractor_id]))


def test_query_answers_blocked_account_question_from_real_retrieval(live_client, mock_ai_apis):
    """DoD expects a citation mentioning "Fintiba or Expatrio" -- this project's
    FintibaSperrkontoAdapter is genuinely about Fintiba, so asserting the retrieved
    content mentions "Fintiba" directly satisfies that either/or condition."""
    _, mock_llm = mock_ai_apis
    fintiba_id = uuid.uuid4()
    distractor_id = uuid.uuid4()
    fintiba_source_url = "https://fintiba.com/sperrkonto-task18-test"

    try:
        _run(_insert_document(
            fintiba_id, fintiba_source_url, "visa",
            "Fintiba provides a blocked account (Sperrkonto) that must hold the required "
            "minimum balance before a German student visa application can be approved.",
            FIXED_EMBEDDING,
        ))
        _run(_insert_document(
            distractor_id, "https://example.com/unrelated", "scholarships",
            "Chevening scholarships are fully funded by the UK government.",
            UNRELATED_EMBEDDING,
        ))

        response = live_client.post("/query", json={
            "question": "How do I open a blocked account from Egypt?",
            "userId": "task18-integration-test-user",
            "topK": 3,
        })

        assert response.status_code == 200
        data = response.json()

        prompt_sent_to_llm = mock_llm.call_args[0][0]
        assert "blocked account" in prompt_sent_to_llm.lower()
        assert "Fintiba" in prompt_sent_to_llm

        cited_urls = {s["source_url"] for s in data["sources"]}
        assert fintiba_source_url in cited_urls
    finally:
        _run(_delete_documents([fintiba_id, distractor_id]))


def test_exact_faq_question_short_circuits(live_client, mock_ai_apis):
    req = {
        "question": "What is a Studienkolleg?",
        "userId": "test-user"
    }
    res = live_client.post("/query", json=req)
    assert res.status_code == 200
    data = res.json()
    # GOA-045 re-curated the seed answers, so this asserts the substance rather
    # than a verbatim string that any future wording change would break.
    assert "preparatory college" in data["answer"]
    assert "Feststellungspr" in data["answer"] or "Abitur" in data["answer"]
    
    _, mock_llm = mock_ai_apis
    assert mock_llm.call_count == 0

def test_paraphrased_faq_question_short_circuits(live_client, mock_ai_apis):
    req = {
        "question": "What is a studienkolleg?",
        "userId": "test-user"
    }
    res = live_client.post("/query", json=req)
    assert res.status_code == 200
    assert "preparatory college" in res.json()["answer"]
    
    _, mock_llm = mock_ai_apis
    assert mock_llm.call_count == 0

def test_unrelated_question_is_refused_not_answered(live_client, mock_ai_apis):
    """An off-corpus question is refused before the LLM, not answered from model memory.

    Renamed from test_unrelated_question_falls_through_to_llm. That name described the
    pre-GOA-033 behaviour -- no FAQ match, so fall through to the LLM -- and after the
    confidence threshold landed it asserted zero LLM calls under a name promising one.
    The assertion is right; the name was not. The fall-through path it used to cover is
    now covered by test_above_threshold_question_reaches_llm below.
    """
    req = {
        "question": "What is the capital of Mongolia?",
        "userId": "test-user"
    }
    res = live_client.post("/query", json=req)
    assert res.status_code == 200

    data = res.json()
    _, mock_llm = mock_ai_apis
    assert data["answer"] is None
    assert data["reason"] == "insufficient_data"
    # The point of the threshold is the call that never happens.
    assert mock_llm.call_count == 0


def test_below_threshold_question_is_refused(live_client, mock_ai_apis):
    """Retrieval below the confidence floor refuses instead of answering weakly."""
    _, mock_llm = mock_ai_apis

    # This one doubles as a false-positive guard: it shares every word but the
    # country with a curated entry about Germany, and scores 0.862 -- which the
    # pre-GOA-045 threshold of 0.85 would have accepted, answering a question
    # about France with German requirements.
    res_below = live_client.post("/query", json={
        "question": "Is the Egyptian Thanaweya Amma certificate recognized for university admission in France?",
        "userId": "test-user"
    })
    assert res_below.status_code == 200
    assert res_below.json()["answer"] is None
    assert res_below.json()["reason"] == "insufficient_data"
    assert mock_llm.call_count == 0
    # A refusal still shows its work -- the user sees what was found and how weak it was.
    assert "sources" in res_below.json()


def test_faq_hit_bypasses_the_confidence_threshold(live_client, mock_ai_apis):
    """A curated FAQ answer is served without being judged by the vector threshold.

    This was previously half of test_threshold_boundary, which after the GOA-033 edits
    tested no boundary at all: the 'below' case was refused and the 'above' case was an
    FAQ short-circuit that never reaches the threshold. The two are separated here
    because they exercise different metrics -- pg_trgm string similarity for the FAQ
    match, cosine similarity for the threshold -- and conflating them is how a change to
    FAQ_SIMILARITY_THRESHOLD would silently start refusing curated answers.
    """
    _, mock_llm = mock_ai_apis

    # Uses a curated alias rather than an ad-hoc paraphrase. GOA-045 raised the
    # match threshold to 0.90 after finding that the looser bar answered a
    # question about FRANCE from the Germany entry (0.862) -- so recall now comes
    # from explicit aliases, and this asserts the FAQ path with one of them.
    res = live_client.post("/query", json={
        "question": "is thanaweya amma accepted in Germany",
        "userId": "test-user"
    })
    assert res.status_code == 200
    assert res.json()["answer"] is not None
    assert "Abitur" in res.json()["answer"]
    assert mock_llm.call_count == 0  # FAQ short-circuit, zero tokens


def test_above_threshold_question_reaches_llm(live_client, mock_ai_apis):
    """Retrieval above the floor must still reach the LLM and produce an answer.

    Coverage restored: after the GOA-033 test edits, every remaining case either was
    refused or short-circuited on the FAQ, so nothing asserted that a good retrieval
    still gets answered. A confidence threshold set too high -- refusing everything --
    would have passed the entire suite without this.

    The document is seeded with FIXED_EMBEDDING, which is the same vector the mocked
    embedding client returns for the query, so cosine similarity is ~1.0 and the result
    clears the 0.60 floor by construction rather than by luck.
    """
    _, mock_llm = mock_ai_apis
    doc_id = uuid.uuid4()

    try:
        _run(_insert_document(
            doc_id, "https://example.com/germany-student-visa", "visa",
            "A German student visa application requires proof of admission, a blocked "
            "account, health insurance and a valid passport.",
            FIXED_EMBEDDING,
        ))

        res = live_client.post("/query", json={
            "question": "What documents are required for a German student visa?",
            "userId": "test-user",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["answer"] is not None
        assert data.get("reason") is None
        assert mock_llm.call_count == 1
    finally:
        _run(_delete_documents([doc_id]))



def test_faq_seed_count(live_client):
    async def get_count():
        conn = await _connect()
        try:
            return await conn.fetchval("SELECT count(*) FROM faq_entries")
        finally:
            await conn.close()
    
    count = _run(get_count())
    assert count >= 30


def test_visa_sources_with_shared_identity_keep_their_own_hashes(live_client):
    source_one_id = uuid.uuid4()
    source_two_id = uuid.uuid4()
    requirement_one_id = uuid.uuid4()
    requirement_two_id = uuid.uuid4()
    source_one = "https://example.test/visa/source-one"
    source_two = "https://example.test/visa/source-two"

    async def seed():
        conn = await asyncpg.connect(dsn=settings.database_url)
        try:
            await conn.execute(
                """
                INSERT INTO visa_sources (
                    id, country, visa_type, issuing_body, source_url, fetch_method, active
                ) VALUES
                    ($1, 'Testland', 'Student', 'Test Ministry', $2, 'httpx', TRUE),
                    ($3, 'Testland', 'Student', 'Test Ministry', $4, 'httpx', TRUE)
                """,
                source_one_id,
                source_one,
                source_two_id,
                source_two,
            )
            await conn.execute(
                """
                INSERT INTO visa_requirements (
                    id, country, visa_type, issuing_body, requirements,
                    source_url, content_hash, egyptian_specific
                ) VALUES
                    ($1, 'Testland', 'Student', 'Test Ministry', '{}'::jsonb,
                     $2, 'hash-one', FALSE),
                    ($3, 'Testland', 'Student', 'Test Ministry', '{}'::jsonb,
                     $4, 'hash-two', FALSE)
                """,
                requirement_one_id,
                source_one,
                requirement_two_id,
                source_two,
            )
        finally:
            await conn.close()

    async def cleanup():
        conn = await asyncpg.connect(dsn=settings.database_url)
        try:
            await conn.execute(
                "DELETE FROM visa_requirements WHERE id = ANY($1::uuid[])",
                [requirement_one_id, requirement_two_id],
            )
            await conn.execute(
                "DELETE FROM visa_sources WHERE id = ANY($1::uuid[])",
                [source_one_id, source_two_id],
            )
        finally:
            await conn.close()

    try:
        _run(seed())
        response = live_client.get(
            "/internal/visa-sources",
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        )
        assert response.status_code == 200
        by_id = {
            source["id"]: source
            for source in response.json()["sources"]
            if source["id"] in {str(source_one_id), str(source_two_id)}
        }
        assert by_id[str(source_one_id)]["content_hash"] == "hash-one"
        assert by_id[str(source_two_id)]["content_hash"] == "hash-two"
    finally:
        _run(cleanup())
