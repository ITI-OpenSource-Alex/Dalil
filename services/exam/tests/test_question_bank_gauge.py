"""Integration tests for the question-bank-size gauge (GOA-066).

Drives the real ``/internal/question-bank/stats`` endpoint with a faked
repository and asserts ``goa_question_bank_size`` tracks the reported bank
contents, including the drain-to-zero case that the endpoint's ``GROUP BY``
stats would otherwise hide.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.api.internal import get_question_repository, router as internal_router


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


class FakeQuestionRepository:
    """Reports whatever rows it is seeded with, exactly like the real
    ``get_question_bank_stats`` GROUP BY: absent pairs produce no row."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    async def get_question_bank_stats(self) -> list[dict[str, Any]]:
        return self.rows

    async def get_question_bank_stats_by_book(self) -> list[dict[str, Any]]:
        return []


def _gauge(skill_area: str, exam_type: str) -> float | None:
    return REGISTRY.get_sample_value(
        "goa_question_bank_size",
        {"skill_area": skill_area, "exam_type": exam_type},
    )


def _client(repo: FakeQuestionRepository) -> TestClient:
    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_question_repository] = lambda: repo
    return TestClient(app)


def test_stats_endpoint_sets_gauge_from_bank_contents() -> None:
    repo = FakeQuestionRepository(
        [
            {"exam_type": "academic", "skill_area": "reading", "count": 7},
            {"exam_type": "general", "skill_area": "listening", "count": 2},
        ]
    )
    client = _client(repo)

    response = client.get("/internal/question-bank/stats", headers=INTERNAL_HEADERS)

    assert response.status_code == 200
    assert _gauge("reading", "academic") == 7.0
    assert _gauge("listening", "general") == 2.0


def test_stats_endpoint_zero_fills_every_known_pair() -> None:
    # An empty bank must publish zeros across the whole grid, not leave pairs
    # absent (mirrors the endpoint's BUG-020 zero-fill).
    client = _client(FakeQuestionRepository([]))

    response = client.get("/internal/question-bank/stats", headers=INTERNAL_HEADERS)

    assert response.status_code == 200
    for skill_area in ("reading", "listening", "writing", "speaking"):
        for exam_type in ("academic", "general"):
            assert _gauge(skill_area, exam_type) == 0.0


def test_gauge_drops_to_zero_when_a_pair_is_drained() -> None:
    # First scrape sees a populated pair; a later scrape after the pair empties
    # must overwrite the stale reading with zero rather than retaining it.
    repo = FakeQuestionRepository(
        [{"exam_type": "academic", "skill_area": "writing", "count": 5}]
    )
    client = _client(repo)

    client.get("/internal/question-bank/stats", headers=INTERNAL_HEADERS)
    assert _gauge("writing", "academic") == 5.0

    repo.rows = []  # the bank is emptied between scrapes
    client.get("/internal/question-bank/stats", headers=INTERNAL_HEADERS)
    assert _gauge("writing", "academic") == 0.0
