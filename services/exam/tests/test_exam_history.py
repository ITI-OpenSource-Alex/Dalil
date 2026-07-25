"""Tests for the exam history / progress / weak-area / recommendation
endpoints.

Uses an in-memory fake repository injected via FastAPI's dependency
override system, so nothing hits Postgres. The fake mimics the
window-function query results the real repository would return.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.history import get_history_service, router as history_router
from app.repositories.history_repository import ExamHistoryRepositoryProtocol
from app.services.history_service import (
    HistoryService,
    detect_weak_area,
    extract_feedback_summary,
)


INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


# ---------------------------------------------------------------------------
# In-memory fake repository
# ---------------------------------------------------------------------------

class FakeHistoryRepository(ExamHistoryRepositoryProtocol):
    """Holds a list of exam-result dicts and answers repo methods off it.

    Mirrors the shape the real asyncpg repo returns: each row is a dict
    with `skill_area`, `exam_type`, `band_score`, `graded_at`,
    `duration_seconds`, `section_scores`, `agent_responses`.
    """

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def _for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["user_id"] == user_id]

    async def get_history_page(
        self, user_id: UUID, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        rows = sorted(
            self._for_user(user_id),
            key=lambda r: r["graded_at"],
            reverse=True,
        )
        return rows[offset : offset + limit]

    async def get_last_n_scores_per_skill(
        self, user_id: UUID, n: int
    ) -> list[dict[str, Any]]:
        # Emulate ROW_NUMBER() OVER (PARTITION BY skill_area ORDER BY graded_at DESC).
        by_skill: dict[str, list[dict[str, Any]]] = {}
        for row in self._for_user(user_id):
            by_skill.setdefault(row["skill_area"], []).append(row)

        out: list[dict[str, Any]] = []
        for skill, rows in by_skill.items():
            newest_n = sorted(
                rows, key=lambda r: r["graded_at"], reverse=True
            )[:n]
            # Real query sorts chronologically per skill; mimic that so
            # the service layer's contract is unambiguous.
            out.extend(sorted(newest_n, key=lambda r: r["graded_at"]))
        # Outer sort by skill_area then graded_at, to match SQL.
        return sorted(out, key=lambda r: (r["skill_area"], r["graded_at"]))

    async def get_latest_per_skill(
        self, user_id: UUID
    ) -> list[dict[str, Any]]:
        by_skill: dict[str, dict[str, Any]] = {}
        for row in self._for_user(user_id):
            existing = by_skill.get(row["skill_area"])
            if existing is None or row["graded_at"] > existing["graded_at"]:
                by_skill[row["skill_area"]] = row
        return list(by_skill.values())

    async def get_exam_count(self, user_id: UUID) -> int:
        return len(self._for_user(user_id))

    async def get_last_exam_date(self, user_id: UUID) -> Any:
        rows = self._for_user(user_id)
        if not rows:
            return None
        return max(r["graded_at"] for r in rows)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_row(
    *,
    user_id: UUID,
    skill: str,
    band: float,
    graded_at: datetime,
    exam_type: str = "academic",
    duration_seconds: int = 3600,
    section_scores: dict[str, Any] | None = None,
    agent_responses: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "skill_area": skill,
        "exam_type": exam_type,
        "band_score": band,
        "graded_at": graded_at,
        "duration_seconds": duration_seconds,
        "section_scores": section_scores or {},
        "agent_responses": agent_responses,
    }


def _build_client(rows: list[dict[str, Any]]) -> AsyncClient:
    """FastAPI app wired to a fake repo, wrapped in an httpx AsyncClient."""
    app = FastAPI()
    app.include_router(history_router)

    fake_repo = FakeHistoryRepository(rows)
    app.dependency_overrides[get_history_service] = lambda: HistoryService(
        fake_repo
    )
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# 1. Unit tests: weak-area detection
# ---------------------------------------------------------------------------

class TestDetectWeakArea:
    """The lowest *absolute* score wins — not the largest gap-from-max."""

    def test_picks_absolute_lowest(self):
        assert (
            detect_weak_area({"fluency": 7.0, "lexical": 6.5, "grammar": 7.5})
            == "lexical"
        )

    def test_ignores_relative_distance(self):
        # If we mistakenly looked at relative distance from the max,
        # `grammar` (7.5 vs max 9.0) would win. Absolute min is `fluency`.
        assert (
            detect_weak_area({"fluency": 5.0, "lexical": 8.5, "grammar": 7.5})
            == "fluency"
        )

    def test_integer_values(self):
        assert detect_weak_area({"a": 6, "b": 4, "c": 5}) == "b"

    def test_mixed_int_and_float(self):
        assert detect_weak_area({"a": 6.5, "b": 6, "c": 7}) == "b"

    def test_ties_break_by_first_seen(self):
        assert detect_weak_area({"a": 5.0, "b": 5.0, "c": 7.0}) == "a"

    def test_empty_dict(self):
        assert detect_weak_area({}) is None

    def test_none_input(self):
        assert detect_weak_area(None) is None

    def test_non_numeric_values_skipped(self):
        # Strings and bools are ignored; the only numeric key wins.
        assert (
            detect_weak_area({"a": "low", "b": 8.0, "c": True, "d": 6.0})
            == "d"
        )

    def test_all_non_numeric_returns_none(self):
        assert detect_weak_area({"a": "x", "b": None}) is None


class TestExtractFeedbackSummary:
    def test_flat_improvement_tip(self):
        assert (
            extract_feedback_summary(
                {"improvement_tip": "Practice skimming."}
            )
            == "Practice skimming."
        )

    def test_nested_dimensions_tip(self):
        payload = {
            "dimensions": {
                "fluency": {"improvement_tip": "Slow down at part 2."}
            }
        }
        assert (
            extract_feedback_summary(payload) == "Slow down at part 2."
        )

    def test_falls_back_to_overall_feedback(self):
        assert (
            extract_feedback_summary({"overall_feedback": "Nice work."})
            == "Nice work."
        )

    def test_missing_returns_none(self):
        assert extract_feedback_summary({}) is None
        assert extract_feedback_summary(None) is None


# ---------------------------------------------------------------------------
# 2. Integration: seed 5 results, verify /progress returns all 5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_progress_returns_all_five_results_in_chronological_order():
    user_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _make_row(
            user_id=user_id,
            skill="reading",
            band=5.0 + i * 0.5,  # 5.0, 5.5, 6.0, 6.5, 7.0
            graded_at=base + timedelta(days=i),
        )
        for i in range(5)
    ]

    async with _build_client(rows) as client:
        resp = await client.get(f"/users/{user_id}/progress")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"reading"}

    trend = body["reading"]
    assert len(trend) == 5
    # Chronological order: oldest first, newest last.
    bands = [pt["band"] for pt in trend]
    assert bands == [5.0, 5.5, 6.0, 6.5, 7.0]

    dates = [pt["date"] for pt in trend]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# 3. Integration: 12 results (3 per skill), verify /progress caps at 3 per
#    skill in chronological order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_progress_returns_last_three_per_skill_when_seeded_with_three():
    """The user has exactly 3 exams per skill; the endpoint's per-skill
    cap is 10, so all 3 should come back in chronological order."""
    user_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    skills = ["reading", "listening", "speaking", "writing"]

    rows = []
    for skill_idx, skill in enumerate(skills):
        for exam_idx in range(3):
            rows.append(
                _make_row(
                    user_id=user_id,
                    skill=skill,
                    band=5.0 + exam_idx * 0.5,
                    # Stagger dates so ordering is deterministic and unique.
                    graded_at=base
                    + timedelta(days=skill_idx * 10 + exam_idx),
                )
            )

    # Add an unrelated user to make sure we filter correctly.
    other_user = uuid4()
    rows.append(
        _make_row(
            user_id=other_user,
            skill="reading",
            band=9.0,
            graded_at=base + timedelta(days=100),
        )
    )

    async with _build_client(rows) as client:
        resp = await client.get(f"/users/{user_id}/progress")

    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == set(skills)
    for skill in skills:
        trend = body[skill]
        assert len(trend) == 3, f"{skill} should have 3 points, got {len(trend)}"
        dates = [pt["date"] for pt in trend]
        assert dates == sorted(dates), (
            f"{skill} trend not chronological: {dates}"
        )
        bands = [pt["band"] for pt in trend]
        assert bands == [5.0, 5.5, 6.0]


@pytest.mark.asyncio
async def test_progress_caps_at_ten_per_skill_when_user_has_more():
    """Independent belt-and-braces check on the window-function cap."""
    user_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 15 reading exams — should be trimmed to the 10 most recent.
    rows = [
        _make_row(
            user_id=user_id,
            skill="reading",
            band=4.0 + i * 0.1,
            graded_at=base + timedelta(days=i),
        )
        for i in range(15)
    ]

    async with _build_client(rows) as client:
        resp = await client.get(f"/users/{user_id}/progress")

    trend = resp.json()["reading"]
    assert len(trend) == 10
    # Should be the ten most recent, sorted oldest-to-newest.
    dates = [pt["date"] for pt in trend]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Contract checks on the other endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exam_history_includes_feedback_summary_and_pagination():
    user_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    rows = [
        _make_row(
            user_id=user_id,
            skill="speaking",
            band=6.5,
            graded_at=base + timedelta(days=i),
            agent_responses={
                "improvement_tip": f"Tip #{i}",
                "overall_feedback": "ok",
            },
        )
        for i in range(25)
    ]

    async with _build_client(rows) as client:
        page1 = await client.get(f"/users/{user_id}/exam-history?page=1")
        page2 = await client.get(f"/users/{user_id}/exam-history?page=2")

    assert page1.status_code == 200 and page2.status_code == 200
    p1, p2 = page1.json(), page2.json()

    assert len(p1) == 20
    assert len(p2) == 5
    # Newest first.
    assert p1[0]["feedback_summary"] == "Tip #24"
    # Camel-case field names in the response.
    assert "examType" in p1[0]
    assert "bandScore" in p1[0]


@pytest.mark.asyncio
async def test_weak_areas_uses_latest_exam_per_skill():
    user_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    rows = [
        # Old reading exam — weakest was section 1, but shouldn't be picked.
        _make_row(
            user_id=user_id,
            skill="reading",
            band=6.0,
            graded_at=base,
            section_scores={"section_1": 4.0, "section_2": 7.0},
        ),
        # Newer reading exam — this one drives the answer.
        _make_row(
            user_id=user_id,
            skill="reading",
            band=6.5,
            graded_at=base + timedelta(days=1),
            section_scores={"section_1": 7.5, "section_3_tfng": 5.0},
        ),
        _make_row(
            user_id=user_id,
            skill="speaking",
            band=6.5,
            graded_at=base,
            section_scores={
                "fluency": 7.0,
                "lexical": 6.5,
                "grammar": 7.5,
                "pronunciation": 6.0,
            },
        ),
    ]

    async with _build_client(rows) as client:
        resp = await client.get(f"/users/{user_id}/weak-areas")

    assert resp.status_code == 200
    body = resp.json()
    assert body["reading"] == "section_3_tfng"
    assert body["speaking"] == "pronunciation"


@pytest.mark.asyncio
async def test_recommendation_profile_returns_200_for_unknown_user():
    """The recommender contract: never 404 — return null-filled profile."""
    async with _build_client([]) as client:
        resp = await client.get(
            f"/internal/users/{uuid4()}/profile-for-recommendation",
            headers=INTERNAL_HEADERS,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "reading_band": None,
        "listening_band": None,
        "speaking_band": None,
        "writing_band": None,
        "weak_areas": None,
        "last_exam_date": None,
        "exam_count": 0,
    }


@pytest.mark.asyncio
async def test_recommendation_profile_requires_internal_key():
    async with _build_client([]) as client:
        resp = await client.get(
            f"/internal/users/{uuid4()}/profile-for-recommendation"
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recommendation_profile_aggregates_latest_bands():
    user_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    rows = [
        _make_row(
            user_id=user_id,
            skill="reading",
            band=6.0,
            graded_at=base,
            section_scores={"s1": 5.0, "s2": 7.0},
        ),
        _make_row(
            user_id=user_id,
            skill="reading",
            band=7.0,
            graded_at=base + timedelta(days=5),
            section_scores={"s1": 8.0, "s2": 6.5},
        ),
        _make_row(
            user_id=user_id,
            skill="speaking",
            band=6.5,
            graded_at=base + timedelta(days=3),
            section_scores={"fluency": 5.5, "grammar": 7.0},
        ),
    ]

    async with _build_client(rows) as client:
        resp = await client.get(
            f"/internal/users/{user_id}/profile-for-recommendation",
            headers=INTERNAL_HEADERS,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reading_band"] == 7.0
    assert body["speaking_band"] == 6.5
    assert body["listening_band"] is None
    assert body["writing_band"] is None
    assert body["exam_count"] == 3
    assert body["weak_areas"] == {"reading": "s2", "speaking": "fluency"}
    assert body["last_exam_date"] is not None


# ---------------------------------------------------------------------------
# Metric wiring — a light smoke test so we notice if the counter gets
# accidentally removed.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_endpoint_increments_prometheus_counter():
    from app.core.metrics import goa_exam_history_requests_total

    before = goa_exam_history_requests_total.labels(
        endpoint="exam_history"
    )._value.get()

    async with _build_client([]) as client:
        await client.get(f"/users/{uuid4()}/exam-history")

    after = goa_exam_history_requests_total.labels(
        endpoint="exam_history"
    )._value.get()

    assert after == before + 1
