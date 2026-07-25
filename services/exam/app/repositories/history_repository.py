"""Repository for read-heavy exam history & progress endpoints.

Uses raw SQL over the existing `asyncpg` pool to match the project's
repository style. Window functions keep the per-skill queries O(1) round
trips (no N+1) — see GOA-074.
"""
from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from asyncpg import Pool


class ExamHistoryRepositoryProtocol(Protocol):
    async def get_history_page(
        self, user_id: UUID, limit: int, offset: int
    ) -> list[dict[str, Any]]: ...

    async def get_last_n_scores_per_skill(
        self, user_id: UUID, n: int
    ) -> list[dict[str, Any]]: ...

    async def get_latest_per_skill(
        self, user_id: UUID
    ) -> list[dict[str, Any]]: ...

    async def get_exam_count(self, user_id: UUID) -> int: ...

    async def get_last_exam_date(self, user_id: UUID) -> Any: ...


class ExamHistoryRepository:
    """PostgreSQL-backed implementation."""

    def __init__(self, pool: Pool) -> None:
        self.pool = pool

    async def get_history_page(
        self, user_id: UUID, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        """Return one page of the user's exams, newest first.

        `exam_type` and the true elapsed duration live on `exam_sessions`,
        so we join it in. `duration_seconds` is derived from the real
        submitted_at - started_at delta when available, falling back to the
        session's configured `time_limit_seconds`.
        """
        query = """
        SELECT
            r.id,
            r.skill_area,
            s.exam_type,
            r.band_score,
            r.graded_at,
            COALESCE(
                EXTRACT(EPOCH FROM (s.submitted_at - s.started_at))::INT,
                s.time_limit_seconds
            ) AS duration_seconds,
            r.agent_responses,
            r.section_scores
        FROM exam_results r
        JOIN exam_sessions s ON s.id = r.session_id
        WHERE r.user_id = $1
        ORDER BY r.graded_at DESC
        LIMIT $2 OFFSET $3
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit, offset)
        return [_row_to_dict(r) for r in rows]

    async def get_last_n_scores_per_skill(
        self, user_id: UUID, n: int
    ) -> list[dict[str, Any]]:
        """Return up to `n` most recent results for each skill_area.

        Uses ROW_NUMBER() OVER (PARTITION BY skill_area ORDER BY graded_at DESC)
        so we hit the DB exactly once regardless of how many skills the user
        has. The outer ORDER BY sorts the result set chronologically per skill
        so the API layer can drop it straight into a chart.
        """
        query = """
        WITH ranked AS (
            SELECT
                skill_area,
                band_score,
                graded_at,
                ROW_NUMBER() OVER (
                    PARTITION BY skill_area
                    ORDER BY graded_at DESC
                ) AS rn
            FROM exam_results
            WHERE user_id = $1
        )
        SELECT skill_area, band_score, graded_at
        FROM ranked
        WHERE rn <= $2
        ORDER BY skill_area ASC, graded_at ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, n)
        return [dict(r) for r in rows]

    async def get_latest_per_skill(
        self, user_id: UUID
    ) -> list[dict[str, Any]]:
        """Return the most recent result per skill_area for `user_id`.

        Same window-function trick with `rn = 1`, so a single query
        returns at most 4 rows.
        """
        query = """
        WITH ranked AS (
            SELECT
                skill_area,
                band_score,
                section_scores,
                graded_at,
                ROW_NUMBER() OVER (
                    PARTITION BY skill_area
                    ORDER BY graded_at DESC
                ) AS rn
            FROM exam_results
            WHERE user_id = $1
        )
        SELECT skill_area, band_score, section_scores, graded_at
        FROM ranked
        WHERE rn = 1
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
        return [_row_to_dict(r) for r in rows]

    async def get_exam_count(self, user_id: UUID) -> int:
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT COUNT(*) FROM exam_results WHERE user_id = $1",
                user_id,
            )
        return int(val or 0)

    async def get_last_exam_date(self, user_id: UUID) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT MAX(graded_at) FROM exam_results WHERE user_id = $1",
                user_id,
            )


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Normalise an asyncpg Record into a plain dict, decoding JSONB text."""
    data = dict(row)
    for key in ("agent_responses", "section_scores"):
        val = data.get(key)
        if isinstance(val, str):
            try:
                data[key] = json.loads(val)
            except (ValueError, TypeError):
                data[key] = None
    return data
