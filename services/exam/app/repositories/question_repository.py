import json
from typing import Any
from uuid import UUID

from asyncpg import Pool, Record


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class QuestionRepository:

    def __init__(self, pool: Pool):
        self.pool = pool

    async def get_random_question(
        self,
        exam_type: str,
        skill_area: str,
        user_id: UUID,
    ) -> Record | None:
        query = """
        SELECT q.*
        FROM questions q
        LEFT JOIN exam_sessions s ON s.question_id = q.id AND s.user_id = $3
        WHERE q.exam_type=$1
          AND q.skill_area=$2
          AND s.id IS NULL
        ORDER BY RANDOM()
        LIMIT 1
        """

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                query,
                exam_type,
                skill_area,
                user_id,
            )

    async def get_answer_key(
        self,
        question_id: UUID,
    ) -> dict[str, Any] | None:
        query = """
        SELECT answer_key
        FROM questions
        WHERE id=$1
        """

        async with self.pool.acquire() as conn:
            answer_key = await conn.fetchval(
                query,
                question_id,
            )
            return _decode_json(answer_key) if answer_key is not None else None

    async def get_by_id(
        self,
        question_id: UUID,
    ) -> Record | None:
        query = """
        SELECT *
        FROM questions
        WHERE id=$1
        """

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, question_id)
