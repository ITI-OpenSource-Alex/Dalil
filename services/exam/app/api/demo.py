"""Service-owned demo reset operations (GOA-047).

The operator script may not write exam_db directly.  This internal endpoint is
the Exam service's narrow, idempotent ownership boundary for the three frozen
Reading-history rows required by the graduation walkthrough.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from app.core.database import db
from app.core.security import validate_internal_api_key


router = APIRouter(
    prefix="/internal/demo",
    tags=["internal-demo"],
    dependencies=[Depends(validate_internal_api_key)],
)

READING_BANDS = ((5.5, 18), (6.0, 23), (6.5, 27))


async def reset_reading_history(user_id: UUID) -> list[dict]:
    now = datetime.now(timezone.utc)
    seeded: list[dict] = []
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT session_id
                FROM exam_results
                WHERE user_id = $1
                  AND skill_area = 'reading'
                  AND agent_responses ->> 'demo_seed' = 'goa-047'
                """,
                user_id,
            )
            session_ids = [row["session_id"] for row in rows]
            if session_ids:
                await conn.execute(
                    "DELETE FROM exam_results WHERE session_id = ANY($1::uuid[])",
                    session_ids,
                )
                await conn.execute(
                    "DELETE FROM exam_sessions WHERE id = ANY($1::uuid[])",
                    session_ids,
                )

            for index, (band, raw_score) in enumerate(READING_BANDS):
                session_id = uuid4()
                result_id = uuid4()
                started_at = now - timedelta(days=3 - index, minutes=60)
                submitted_at = started_at + timedelta(minutes=55)
                await conn.execute(
                    """
                    INSERT INTO exam_sessions (
                        id, user_id, exam_type, skill_area, status, started_at,
                        submitted_at, time_limit_seconds, question_id,
                        last_heartbeat_at
                    ) VALUES ($1, $2, 'academic', 'reading', 'scored', $3,
                              $4, 3600, NULL, $4)
                    """,
                    session_id,
                    user_id,
                    started_at,
                    submitted_at,
                )
                await conn.execute(
                    """
                    INSERT INTO exam_results (
                        id, session_id, user_id, skill_area, raw_score,
                        band_score, section_scores, graded_at, agent_responses
                    ) VALUES ($1, $2, $3, 'reading', $4, $5, $6::jsonb, $7,
                              $8::jsonb)
                    """,
                    result_id,
                    session_id,
                    user_id,
                    raw_score,
                    band,
                    json.dumps({"demo": True}),
                    submitted_at,
                    json.dumps({"demo_seed": "goa-047"}),
                )
                seeded.append(
                    {
                        "session_id": str(session_id),
                        "band_score": band,
                        "graded_at": submitted_at.isoformat(),
                    }
                )
    return seeded


@router.post("/users/{user_id}/reading-history/reset")
async def reset_demo_reading_history(user_id: UUID):
    return {"history": await reset_reading_history(user_id)}
