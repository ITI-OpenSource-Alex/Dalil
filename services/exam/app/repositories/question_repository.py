import json
from typing import Any
from uuid import UUID

import structlog
from asyncpg import Pool, Record

logger = structlog.get_logger("exam_service.question_repository")


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


# A test is servable only if every question it shows can actually be scored.
#
# Reading and Listening are graded deterministically against answer_key, and the
# parsed bank is badly under-keyed: IELTS-17 test 1 presents 40 questions with a
# single key, so a candidate answering all 40 correctly scores raw 1 -> band 0.0
# (BUG-050). Counting questions alone is not enough — BUG-021's guard let those
# through because the questions array is full; it is the key array that is short.
#
# Speaking and Writing are LLM-graded and carry no answer_key at all, so the
# check must be skill-aware or it would make them unservable too.
#
# This is deliberately strict rather than a percentage threshold: a partially
# scorable exam produces a confidently wrong band, which is worse than no exam.
# It currently leaves 4 reading tests servable and 0 listening tests — listening
# being unavailable is correct, since its audio bucket is empty as well
# (BUG-022), so every listening session was already broken end to end.
_SCORABLE_CLAUSE = """
          AND (
                q.skill_area NOT IN ('reading', 'listening')
             OR (SELECT count(*) FROM jsonb_object_keys(q.answer_key))
                = jsonb_array_length(q.questions)
          )
"""


class QuestionRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def get_random_question(
        self,
        exam_type: str,
        skill_area: str,
        user_id: UUID,
    ) -> Record | None:
        # Same guard as get_random_unseen_question: a test with no questions must
        # never be handed to a candidate. 11 of 20 writing tests and 6 of 21
        # speaking tests parsed with zero questions, so this path returned sessions
        # whose first_question_set was literally `"questions": []` (BUG-021).
        query = f"""
        SELECT q.*
        FROM questions q
        LEFT JOIN exam_sessions s ON s.question_id = q.id AND s.user_id = $3
        WHERE q.exam_type=$1
          AND q.skill_area=$2
          AND jsonb_array_length(q.questions) > 0
          {_SCORABLE_CLAUSE}
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
        # jsonb_array_length > 0 keeps unusable tests out of circulation. Three
        # reading tests parsed as book_ref `IELTS-unknown` with zero questions and
        # the ingest script inserted them while reporting "Errors: 0"; a candidate
        # who drew one got a created session, a running clock and nothing to
        # answer (BUG-021). This guard belongs on the read path regardless of what
        # ingestion lets through.
        query = f"""
        SELECT q.*
        FROM questions q
        WHERE q.exam_type=$1
          AND q.skill_area=$2
          AND jsonb_array_length(q.questions) > 0
          {_SCORABLE_CLAUSE}
          AND q.id NOT IN (
              SELECT question_id FROM exam_sessions WHERE user_id=$3
          )
        ORDER BY RANDOM()
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, exam_type, skill_area, user_id)
            if row is None:
                await self._log_why_nothing_servable(conn, exam_type, skill_area)
        return row

    async def _log_why_nothing_servable(self, conn, exam_type: str, skill_area: str) -> None:
        """Explain an empty selection instead of letting it read as an empty bank.

        "No reading tests available" is the same message whether nothing was ever
        ingested or seventeen tests exist and every one is unscorable. An operator
        needs to tell those apart — that ambiguity is what let BUG-050 sit
        unnoticed behind a plausible-looking 404.
        """
        stats = await conn.fetchrow(
            """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE jsonb_array_length(questions) = 0) AS no_questions,
                   count(*) FILTER (
                       WHERE jsonb_array_length(questions) > 0
                         AND (SELECT count(*) FROM jsonb_object_keys(answer_key))
                             <> jsonb_array_length(questions)
                   ) AS incomplete_keys
            FROM questions
            WHERE exam_type = $1 AND skill_area = $2
            """,
            exam_type,
            skill_area,
        )
        if stats and stats["total"]:
            logger.warning(
                "no_servable_test_found",
                exam_type=exam_type,
                skill_area=skill_area,
                tests_in_bank=stats["total"],
                excluded_no_questions=stats["no_questions"],
                excluded_incomplete_answer_key=stats["incomplete_keys"],
                detail="tests exist but none are fully scorable; see BUG-050",
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
        ON CONFLICT (book_ref, test_number, skill_area) DO UPDATE SET
            passage_text = EXCLUDED.passage_text,
            audio_s3_key = EXCLUDED.audio_s3_key,
            questions = EXCLUDED.questions,
            answer_key = EXCLUDED.answer_key
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
