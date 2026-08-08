import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from pgvector.asyncpg import register_vector

from app.core import database
from app.core.config import settings
from app.core.metrics import RETRIEVAL_ARM_HITS
from app.services import rag_service


MIGRATIONS = Path(__file__).parents[1] / "app" / "migrations"


async def _connection():
    connection = await asyncpg.connect(settings.database_url)
    await register_vector(connection)
    return connection


@pytest.mark.asyncio
async def test_tsvector_column_is_generated():
    connection = await _connection()
    transaction = connection.transaction()
    await transaction.start()
    try:
        document_id = await connection.fetchval(
            """
            INSERT INTO documents (title, content, source_url, category)
            VALUES ('GOA-137 generated vector', 'Chevening EPOS punctuation', 'test://goa-137', 'scholarships')
            RETURNING id
            """
        )
        value = await connection.fetchval(
            "SELECT content_tsv::text FROM documents WHERE id = $1", document_id
        )
        assert "cheven" in value
        assert "'epo'" in value
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_tsvector_updates_on_content_change():
    connection = await _connection()
    transaction = connection.transaction()
    await transaction.start()
    try:
        document_id = await connection.fetchval(
            """
            INSERT INTO documents (title, content, source_url, category)
            VALUES ('GOA-137 update vector', 'Chevening', 'test://goa-137-update', 'scholarships')
            RETURNING id
            """
        )
        await connection.execute(
            "UPDATE documents SET content = 'Thanaweya replacement' WHERE id = $1",
            document_id,
        )
        value = await connection.fetchval(
            "SELECT content_tsv::text FROM documents WHERE id = $1", document_id
        )
        assert "thanaweya" in value
        assert "cheven" not in value
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_gin_index_is_used():
    connection = await _connection()
    try:
        async with connection.transaction():
            await connection.execute("SET LOCAL enable_seqscan = off")
            rows = await connection.fetch(
                """
                EXPLAIN SELECT id FROM documents
                WHERE content_tsv @@ websearch_to_tsquery('english', 'Chevening')
                LIMIT 15
                """
            )
        plan = "\n".join(row[0] for row in rows)
        assert "Bitmap Index Scan on documents_content_tsv_idx" in plan
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_websearch_to_tsquery_handles_user_punctuation():
    connection = await _connection()
    try:
        parsed = await connection.fetchval(
            "SELECT websearch_to_tsquery('english', $1)::text",
            '"DAAD EPOS" eligibility -undergraduate?',
        )
        assert parsed
    finally:
        await connection.close()


def _candidate(document_id: str, similarity: float = 0.8):
    return {
        "id": document_id,
        "title": document_id,
        "content": f"content {document_id}",
        "source_url": f"test://{document_id}",
        "similarity": similarity,
    }


def _lexical(document_id: str, score: float = 0.4):
    candidate = _candidate(document_id)
    candidate.pop("similarity")
    candidate["lexical_score"] = score
    return candidate


def test_rrf_fusion_ranks():
    fused = rag_service.reciprocal_rank_fusion(
        [_candidate("a"), _candidate("b")],
        [_lexical("b"), _lexical("a")],
    )
    assert [item["id"] for item in fused] == ["a", "b"]
    assert fused[0]["rrf_score"] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_handles_disjoint_arms():
    fused = rag_service.reciprocal_rank_fusion(
        [_candidate("dense-a"), _candidate("dense-b")],
        [_lexical("lexical-a"), _lexical("lexical-b")],
    )
    assert len(fused) == 4
    assert len({item["id"] for item in fused}) == 4
    lexical_only = next(item for item in fused if item["id"] == "lexical-a")
    assert lexical_only["similarity"] is None
    assert lexical_only["retrieval_arms"] == ["lexical"]


def test_rrf_rewards_documents_in_both_arms():
    dense = [_candidate("dense-first"), _candidate("x"), _candidate("both")]
    lexical = [_lexical("lexical-first"), _lexical("y"), _lexical("both")]
    fused = rag_service.reciprocal_rank_fusion(dense, lexical)
    ranks = {item["id"]: rank for rank, item in enumerate(fused, 1)}
    assert ranks["both"] < ranks["dense-first"]
    assert ranks["both"] < ranks["lexical-first"]


def _mock_pool(fetch_side_effect):
    connection = AsyncMock()
    connection.fetch = AsyncMock(side_effect=fetch_side_effect)
    connection.fetchrow = AsyncMock(return_value=None)
    connection.execute = AsyncMock(return_value=None)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    connection.transaction = MagicMock(return_value=transaction)
    acquired = MagicMock()
    acquired.__aenter__ = AsyncMock(return_value=connection)
    acquired.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquired)
    return pool, connection, transaction


@pytest.mark.asyncio
async def test_hybrid_runs_inside_transaction(monkeypatch):
    dense = [_candidate("dense")]
    lexical = [_lexical("lexical")]
    pool, connection, transaction = _mock_pool([dense, lexical])
    monkeypatch.setattr(rag_service.db, "pool", pool)
    monkeypatch.setattr(rag_service, "generate_embedding", AsyncMock(return_value=[0.1] * 768))
    monkeypatch.setattr(rag_service, "_find_faq_match", AsyncMock(return_value=None))

    await rag_service.query_rag(
        "DAAD EPOS",
        "test",
        flag_overrides={
            "hybrid_enabled": True,
            "ivfflat_probes": 10,
            "threshold_enabled": False,
            "rerank_enabled": False,
            "retrieval_only": True,
        },
    )

    transaction.__aenter__.assert_awaited_once()
    connection.execute.assert_awaited_once_with("SET LOCAL ivfflat.probes = 10;")
    assert connection.fetch.await_count == 2
    transaction.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_category_filter_applies_to_both_arms():
    dense_sql, lexical_sql = rag_service._retrieval_sql("scholarships")
    connection = await _connection()
    try:
        vector = await connection.fetchval(
            "SELECT embedding FROM documents WHERE category = 'scholarships' LIMIT 1"
        )
        dense_rows = await connection.fetch(
            dense_sql, vector, 15, "scholarships"
        )
        lexical_rows = await connection.fetch(
            lexical_sql, "Chevening", 15, "scholarships"
        )
        ids = [row["id"] for row in [*dense_rows, *lexical_rows]]
        categories = await connection.fetch(
            "SELECT DISTINCT category FROM documents WHERE id = ANY($1::uuid[])", ids
        )
        assert ids
        assert {row["category"] for row in categories} == {"scholarships"}
    finally:
        await connection.close()


def test_no_category_filter_when_unset():
    dense_sql, lexical_sql = rag_service._retrieval_sql(None)
    assert "category =" not in dense_sql
    assert "category =" not in lexical_sql
    assert "$3" not in dense_sql
    assert "$3" not in lexical_sql


@pytest.mark.asyncio
async def test_confidence_threshold_still_uses_dense_similarity(monkeypatch):
    dense = [_candidate("dense-low", similarity=0.50)]
    lexical = [_lexical("lexical-perfect", score=999.0)]
    pool, _, _ = _mock_pool([dense, lexical])
    monkeypatch.setattr(rag_service.db, "pool", pool)
    monkeypatch.setattr(rag_service, "generate_embedding", AsyncMock(return_value=[0.1] * 768))
    monkeypatch.setattr(rag_service, "_find_faq_match", AsyncMock(return_value=None))

    answer, sources, metrics = await rag_service.query_rag(
        "Chevening",
        "test",
        flag_overrides={
            "hybrid_enabled": True,
            "threshold_enabled": True,
            "rerank_enabled": False,
            "retrieval_only": True,
        },
    )

    assert answer is None
    assert metrics["refused"] is True
    assert metrics["top_similarity"] == 0.50
    assert any(source["id"] == "lexical-perfect" for source in sources)


@pytest.mark.asyncio
async def test_hybrid_flag_disables_lexical_arm(monkeypatch):
    dense = [_candidate("dense-only", similarity=0.85)]
    pool, connection, _ = _mock_pool([dense])
    monkeypatch.setattr(rag_service.db, "pool", pool)
    monkeypatch.setattr(rag_service, "generate_embedding", AsyncMock(return_value=[0.1] * 768))
    monkeypatch.setattr(rag_service, "_find_faq_match", AsyncMock(return_value=None))

    _, sources, _ = await rag_service.query_rag(
        "dense path",
        "test",
        flag_overrides={
            "hybrid_enabled": False,
            "threshold_enabled": False,
            "rerank_enabled": False,
            "retrieval_only": True,
        },
    )

    assert connection.fetch.await_count == 1
    assert sources == [
        {
            "id": "dense-only",
            "title": "dense-only",
            "content": "content dense-only",
            "source_url": "test://dense-only",
            "similarity": 0.85,
            "relevance_score": 0.85,
        }
    ]


def test_retrieval_arm_hits_metric():
    labels = ("dense_only", "lexical_only", "both")
    before = {
        label: RETRIEVAL_ARM_HITS.labels(arm=label)._value.get() for label in labels
    }
    rag_service._record_retrieval_arm_hits(
        [
            {"retrieval_arms": ["dense"]},
            {"retrieval_arms": ["lexical"]},
            {"retrieval_arms": ["dense", "lexical"]},
        ]
    )
    after = {
        label: RETRIEVAL_ARM_HITS.labels(arm=label)._value.get() for label in labels
    }
    assert after == {label: before[label] + 1 for label in labels}


def test_migration_number_is_unique(caplog):
    migration_paths = sorted(MIGRATIONS.glob("*.sql"))
    duplicates = database.duplicate_migration_prefixes(migration_paths)
    new_migrations = [path for path in migration_paths if path.name.startswith("030_")]
    assert [path.name for path in new_migrations] == [
        "030_add_documents_full_text_search.sql"
    ]
    assert "030" not in duplicates

    with caplog.at_level(logging.WARNING, logger="rag_service.database"):
        database.logger.warning(
            "Existing duplicate migration number prefixes: %s", duplicates
        )
    assert "027" in caplog.text
    assert "028" in caplog.text
