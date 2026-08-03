"""
evals/tests/test_rag_retrieval_eval.py

Unit tests for retrieval evaluation metrics: relevant_at_1, recall_at_15, and reciprocal_rank.
"""

import pytest
from evals.rag_retrieval_eval import relevant_at_1, recall_at_15, reciprocal_rank


def test_relevant_at_1_hit():
    """Verify relevant_at_1 returns 1.0 when results[0] is in relevant_ids."""
    results = ["doc-100", "doc-200", "doc-300"]
    relevant_ids = {"doc-100", "doc-999"}
    assert relevant_at_1(results, relevant_ids) == 1.0


def test_relevant_at_1_miss():
    """Verify relevant_at_1 returns 0.0 when results[0] is not in relevant_ids."""
    results = ["doc-200", "doc-100", "doc-300"]
    relevant_ids = {"doc-100"}
    assert relevant_at_1(results, relevant_ids) == 0.0


def test_relevant_at_1_empty():
    """Verify relevant_at_1 returns 0.0 on empty inputs."""
    assert relevant_at_1([], {"doc-100"}) == 0.0
    assert relevant_at_1(["doc-100"], set()) == 0.0


def test_recall_at_15_partial_and_full():
    """Verify recall_at_15 calculates fraction of ground-truth relevant_ids present in top-15."""
    results = [f"doc-{i}" for i in range(1, 16)]
    # Ground truth has 4 items, 2 of which are in top 15 (doc-1, doc-5)
    relevant_ids = {"doc-1", "doc-5", "doc-99", "doc-100"}
    assert recall_at_15(results, relevant_ids) == 0.5  # 2 out of 4 = 50%


def test_reciprocal_rank():
    """Verify reciprocal rank calculation at various positions."""
    results = ["doc-a", "doc-b", "doc-c", "doc-d"]
    
    # Hit at position 1 (1 / 1 = 1.0)
    assert reciprocal_rank(results, {"doc-a"}) == 1.0

    # Hit at position 2 (1 / 2 = 0.5)
    assert reciprocal_rank(results, {"doc-b"}) == 0.5

    # Hit at position 3 (1 / 3 = 0.333...)
    assert reciprocal_rank(results, {"doc-c"}) == pytest.approx(1.0 / 3.0)

    # Miss (0.0)
    assert reciprocal_rank(results, {"doc-z"}) == 0.0
