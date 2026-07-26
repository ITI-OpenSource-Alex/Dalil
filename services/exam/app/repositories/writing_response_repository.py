import json
from typing import Any
from uuid import UUID

from asyncpg import Pool, Record


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class WritingResponseRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def save_response(
        self,
        session_id: UUID,
        task_number: int,
        response_text: str,
        word_count: int,
        penalty_flag: bool = False,
    ) -> Record:
        """
        Insert a new writing response, or overwrite it if the student
        resubmits the same task (retry-safe on the unique_session_writing_task
        constraint).
        """
        query = """
        INSERT INTO exam_writing_responses (
            session_id, task_number, response_text, word_count, penalty_flag
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (session_id, task_number)
        DO UPDATE SET
            response_text = EXCLUDED.response_text,
            word_count = EXCLUDED.word_count,
            penalty_flag = EXCLUDED.penalty_flag,
            evaluation_result = NULL,
            created_at = NOW()
        RETURNING *
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                query,
                session_id,
                task_number,
                response_text,
                word_count,
                penalty_flag,
            )

    async def save_evaluation(
        self,
        session_id: UUID,
        task_number: int,
        evaluation_result: dict[str, Any],
    ) -> Record | None:
        """
        Attach the grading/evaluation result to an existing submission.
        """
        query = """
        UPDATE exam_writing_responses
        SET evaluation_result = $3
        WHERE session_id = $1 AND task_number = $2
        RETURNING *
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                query,
                session_id,
                task_number,
                json.dumps(evaluation_result),
            )

    async def get_by_session_and_task(
        self,
        session_id: UUID,
        task_number: int,
    ) -> Record | None:
        query = """
        SELECT *
        FROM exam_writing_responses
        WHERE session_id = $1 AND task_number = $2
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, session_id, task_number)

    async def get_all_by_session(
        self,
        session_id: UUID,
    ) -> list[Record]:
        query = """
        SELECT *
        FROM exam_writing_responses
        WHERE session_id = $1
        ORDER BY task_number
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, session_id)

    async def get_evaluation(
        self,
        session_id: UUID,
        task_number: int,
    ) -> dict[str, Any] | None:
        query = """
        SELECT evaluation_result
        FROM exam_writing_responses
        WHERE session_id = $1 AND task_number = $2
        """
        async with self.pool.acquire() as conn:
            evaluation_result = await conn.fetchval(query, session_id, task_number)
            return (
                _decode_json(evaluation_result)
                if evaluation_result is not None
                else None
            )
