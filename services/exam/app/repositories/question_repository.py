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

    async def get_random_unseen_question(
        self,
        exam_type: str,
        skill_area: str,
        user_id: UUID,
    ) -> Record | None:
        query = """
        SELECT q.*
        FROM questions q
        WHERE q.exam_type=$1
          AND q.skill_area=$2
          AND q.id NOT IN (
              SELECT question_id FROM exam_sessions WHERE user_id=$3
          )
        ORDER BY RANDOM()
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, exam_type, skill_area, user_id)
        if row is not None:
            return row
        return await self.get_random_question(exam_type, skill_area)

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

    async def upsert_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = """
        INSERT INTO questions (
            book_ref,
            test_number,
            exam_type,
            skill_area,
            passage_text,
            audio_s3_key,
            questions,
            answer_key
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
        ON CONFLICT (book_ref, test_number, skill_area) DO NOTHING
        RETURNING *
        """

        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                query,
                payload["book_ref"],
                payload["test_number"],
                payload.get("exam_type", "academic"),
                payload.get("skill_area", "reading"),
                payload.get("passage_text"),
                payload.get("audio_s3_key"),
                json.dumps(payload.get("questions", [])),
                json.dumps(payload.get("answer_key", {})),
            )
            if record is not None:
                return dict(record)

        existing = await self.get_by_unique_key(
            payload["book_ref"],
            payload["test_number"],
            payload.get("skill_area", "reading"),
        )
        if existing is not None:
            return dict(existing)
        return payload

    async def get_by_unique_key(
        self,
        book_ref: str,
        test_number: int,
        skill_area: str,
    ) -> Record | None:
        query = """
        SELECT *
        FROM questions
        WHERE book_ref=$1
          AND test_number=$2
          AND skill_area=$3
        LIMIT 1
        """

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, book_ref, test_number, skill_area)

    async def get_question_bank_stats(self) -> list[dict[str, Any]]:
        query = """
        SELECT exam_type, skill_area, COUNT(*) AS count
        FROM questions
        GROUP BY exam_type, skill_area
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def get_question_bank_stats_by_book(self) -> list[dict[str, Any]]:
        query = """
        SELECT book_ref, exam_type, skill_area, COUNT(*) AS count
        FROM questions
        GROUP BY book_ref, exam_type, skill_area
        ORDER BY book_ref, exam_type, skill_area
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
