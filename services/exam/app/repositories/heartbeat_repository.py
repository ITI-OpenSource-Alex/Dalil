from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from asyncpg import Pool


@runtime_checkable
class HeartbeatRepositoryProtocol(Protocol):
    async def get_session_for_heartbeat(
        self, session_id: UUID
    ) -> dict[str, Any] | None: ...

    async def touch_heartbeat(self, session_id: UUID) -> None: ...

    async def sweep_abandoned(
        self, grace_minutes: int = 10
    ) -> tuple[int, list[dict[str, Any]]]: ...


class HeartbeatRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def get_session_for_heartbeat(
        self, session_id: UUID
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, status FROM exam_sessions WHERE id = $1",
                session_id,
            )
            return dict(row) if row else None

    async def touch_heartbeat(self, session_id: UUID) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE exam_sessions SET last_heartbeat_at = NOW() "
                "WHERE id = $1 AND status = 'in_progress'",
                session_id,
            )

    async def sweep_abandoned(
        self, grace_minutes: int = 10
    ) -> tuple[int, list[dict[str, Any]]]:
        """Mark silent in-progress sessions as abandoned.

        `grace_minutes` is how long a session may go without a heartbeat, not
        how long it may run. Those are different questions, and conflating them
        is what made the original sweep dangerous: it abandoned any session whose
        `started_at` was more than 10 minutes ago whenever `last_heartbeat_at`
        was NULL. A reading exam is 60 minutes and no client sent heartbeats, so
        every candidate would have been marked abandoned at minute 10 and met a
        403 on submit, losing the attempt (BUG-054).

        Two cases, deliberately asymmetric:

        - The session has heartbeated. Trust it: silence beyond the grace window
          means the tab is gone.
        - The session has never heartbeated. Fall back to the session's own
          `time_limit_seconds` plus the grace window, so a client that cannot or
          does not heartbeat still gets its full exam. This is the safety net
          that keeps a client-side regression from costing candidates their
          attempts, and it derives from the row rather than a constant -- a
          60-minute exam and a 40-minute one should not share one.
        """
        async with self.pool.acquire() as conn:
            checked = await conn.fetchval(
                "SELECT COUNT(*) FROM exam_sessions WHERE status = 'in_progress'"
            )
            rows = await conn.fetch(
                """
                UPDATE exam_sessions
                SET status = 'abandoned'
                WHERE status = 'in_progress'
                  AND (
                    (
                      last_heartbeat_at IS NOT NULL
                      AND last_heartbeat_at < NOW() - make_interval(mins => $1)
                    )
                    OR (
                      last_heartbeat_at IS NULL
                      AND started_at < NOW()
                                       - make_interval(secs => time_limit_seconds)
                                       - make_interval(mins => $1)
                    )
                  )
                RETURNING id, skill_area, exam_type
                """,
                grace_minutes,
            )
            return checked, [dict(r) for r in rows]
