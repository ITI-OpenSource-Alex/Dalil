"""GOA-030 — the ANN probe default is a correctness guard, not a tuning knob.

Journey 2 requires a student-visa answer to cite the official government or
embassy URL that was fetched. Against the live catalogue it cited none: the
Germany student-visa question returned four MastersPortal programme pages and
zero visa documents.

The corpus was not the problem and neither was the embedding -- the correct
EU-immigration-portal chunk scores 0.854, the highest similarity in the whole
corpus. `documents_embedding_idx` is IVFFlat with lists=100, and
`rag_ivfflat_probes` was 1, so the query scanned a single cluster and the visa
cluster was never among them.

These tests pin the two things that made that failure possible and invisible:
the default itself, and the fact that it is actually applied to the query.
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.services import rag_service


MIGRATIONS = Path(__file__).parents[1] / "app" / "migrations"


def _index_lists() -> int:
    """The lists= the embedding index is actually built with, read from SQL.

    Parsed rather than hardcoded: the coupling between probes and lists is the
    whole point, and a test that restated lists from memory could agree with
    itself while disagreeing with the index.
    """
    pattern = re.compile(
        r"documents_embedding_idx.*?ivfflat.*?lists\s*=\s*'?(\d+)'?",
        re.IGNORECASE | re.DOTALL,
    )
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = pattern.search(path.read_text(encoding="utf-8"))
        if match:
            return int(match.group(1))
    raise AssertionError(
        "No CREATE INDEX ... ivfflat ... lists=N found for documents_embedding_idx. "
        "If the index moved to HNSW, this guard needs rewriting, not deleting."
    )


def test_probe_default_is_sqrt_of_index_lists():
    """probes must track the index, and must never fall back to 1.

    pgvector's guidance for IVFFlat is probes = sqrt(lists). At lists=100 that
    is 10, which measured recall@5 = 1.00 against the live catalogue where
    probes=1 measured 0.25 on visa questions.
    """
    lists = _index_lists()
    expected = round(lists**0.5)
    assert settings.rag_ivfflat_probes == expected, (
        f"documents_embedding_idx is built with lists={lists}, so probes should "
        f"be sqrt(lists)={expected}, not {settings.rag_ivfflat_probes}. If the "
        f"index changed, re-run perf/rag_probes_bench.py and update both."
    )
    assert settings.rag_ivfflat_probes > 1, (
        "probes=1 scans one cluster of the index. It is pgvector's build-time "
        "default, not a tuned value, and it silently drops whole categories "
        "from retrieval when one category dominates the corpus."
    )


def _mock_pool(fetch_results):
    connection = MagicMock()
    connection.fetch = AsyncMock(side_effect=fetch_results)
    connection.execute = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    connection.transaction = MagicMock(return_value=transaction)
    acquired = MagicMock()
    acquired.__aenter__ = AsyncMock(return_value=connection)
    acquired.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquired)
    return pool, connection


@pytest.mark.asyncio
async def test_configured_probes_are_applied_without_an_explicit_override(monkeypatch):
    """The default must reach the query, not just sit in the settings object.

    The original defect had two halves. GOA-137 fixed one -- SET LOCAL outside a
    transaction is discarded, so the statement was a no-op. This asserts the
    other half: with no per-request override at all, the configured default is
    still what Postgres is told to use.
    """
    pool, connection = _mock_pool([[]])
    monkeypatch.setattr(rag_service.db, "pool", pool)
    monkeypatch.setattr(
        rag_service, "generate_embedding", AsyncMock(return_value=[0.1] * 768)
    )
    monkeypatch.setattr(rag_service, "_find_faq_match", AsyncMock(return_value=None))

    await rag_service.query_rag(
        "What are the student visa requirements for Germany?",
        "test-user",
        # Deliberately no ivfflat_probes here: the point is the DEFAULT path.
        flag_overrides={
            "threshold_enabled": False,
            "rerank_enabled": False,
            "retrieval_only": True,
        },
    )

    connection.execute.assert_awaited_once_with(
        f"SET LOCAL ivfflat.probes = {settings.rag_ivfflat_probes};"
    )
