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
        self, threshold_minutes: int = 10
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
        self, threshold_minutes: int = 10
    ) -> tuple[int, list[dict[str, Any]]]:
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
                    last_heartbeat_at < NOW() - make_interval(mins => $1)
                    OR (
                      last_heartbeat_at IS NULL
                      AND started_at < NOW() - make_interval(mins => $1)
                    )
                  )
                RETURNING id, skill_area, exam_type
                """,
                threshold_minutes,
            )
            return checked, [dict(r) for r in rows]
