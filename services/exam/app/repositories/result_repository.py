import json
from typing import Any
from uuid import UUID

from asyncpg import Pool, Record


class ResultRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def create(
        self,
        result_id: UUID,
        session_id: UUID,
        user_id: UUID,
        skill_area: str,
        raw_score: int,
        band_score: float,
        section_scores: dict[str, Any],
        agent_responses: dict | list | None = None,
    ) -> None:
        query = """
        INSERT INTO exam_results(
            id,
            session_id,
            user_id,
            skill_area,
            raw_score,
            band_score,
            section_scores,
            graded_at,
            agent_responses
        )
        VALUES(
            $1,$2,$3,$4,$5,$6,$7::jsonb,NOW(),$8::jsonb
        )
        """
        if agent_responses is not None:
            agent_responses = json.dumps(agent_responses)

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                result_id,
                session_id,
                user_id,
                skill_area,
                raw_score,
                band_score,
                json.dumps(section_scores) if section_scores else None,
                agent_responses,
            )

    async def get_by_session(
        self,
        session_id: UUID,
    ) -> Record | None:
        query = """
        SELECT *
        FROM exam_results
        WHERE session_id=$1
        """

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, session_id)
