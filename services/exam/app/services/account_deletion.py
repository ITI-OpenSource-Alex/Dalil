from __future__ import annotations

import json
from typing import Any
from uuid import UUID


def parse_account_deleted_event(message_body: str | dict[str, Any]) -> str | None:
    event = json.loads(message_body) if isinstance(message_body, str) else message_body
    if event.get("Type") == "Notification" and event.get("Message"):
        event = json.loads(event["Message"])
    if event.get("type") != "account.deleted":
        return None
    return event.get("payload", {}).get("userId")


async def purge_user_data(pool: Any, user_id: str) -> dict[str, int]:
    user_uuid = UUID(user_id)
    async with pool.acquire() as conn:
        async with conn.transaction():
            results = await conn.execute("DELETE FROM exam_results WHERE user_id = $1", user_uuid)
            sessions = await conn.execute("DELETE FROM exam_sessions WHERE user_id = $1", user_uuid)
    return {
        "examResultsDeleted": int(results.split()[-1]),
        "examSessionsDeleted": int(sessions.split()[-1]),
    }


async def export_user_data(pool: Any, user_id: str) -> dict[str, list[dict[str, Any]]]:
    user_uuid = UUID(user_id)
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT id, session_id, user_id, skill_area, raw_score, band_score,
                   max_score, answers, detailed_results, graded_at
            FROM exam_results
            WHERE user_id = $1
            ORDER BY graded_at DESC
            """,
            user_uuid,
        )
        sessions = await conn.fetch(
            """
            SELECT id, user_id, skill_area, status, started_at, completed_at
            FROM exam_sessions
            WHERE user_id = $1
            ORDER BY started_at DESC
            """,
            user_uuid,
        )
    return {
        "results": [dict(row) for row in results],
        "sessions": [dict(row) for row in sessions],
    }
