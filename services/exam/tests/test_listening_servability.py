"""Real-Postgres regression coverage for Listening question selection.

The curated Listening bank stores metadata alongside the actual answer map::

    {"answers": {"1": "..."}, "unordered_groups": [["21", "22"]]}

Selection must compare the number of questions with the nested ``answers``
object. A fake repository cannot catch a malformed SQL predicate, so this test
uses a loop-local pool and temporary tables in a real PostgreSQL connection.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.repositories.question_repository import QuestionRepository


async def _temporary_question_pool():
    import asyncpg

    from app.core.config import settings

    try:
        pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=1,
        )
    except Exception:
        pytest.skip("Database not available for Listening servability integration test")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TEMP TABLE questions (
                id UUID PRIMARY KEY,
                book_ref TEXT NOT NULL,
                test_number INTEGER NOT NULL,
                exam_type TEXT NOT NULL,
                skill_area TEXT NOT NULL,
                passage_text TEXT,
                audio_s3_key TEXT,
                answer_key JSONB NOT NULL,
                questions JSONB NOT NULL
            );
            CREATE TEMP TABLE exam_sessions (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL,
                question_id UUID,
                status TEXT NOT NULL DEFAULT 'in_progress'
            );
            """
        )

    return pool


@pytest.mark.asyncio
async def test_nested_listening_answer_map_is_servable() -> None:
    pool = await _temporary_question_pool()
    question_id = uuid4()
    user_id = uuid4()
    questions = [
        {
            "number": number,
            "prompt": f"Question {number}",
            "question_type": "Sentence Completion",
            "section_number": 1,
        }
        for number in range(1, 4)
    ]
    answer_key = {
        "answers": {"1": "alpha", "2": "beta", "3": "gamma"},
        "unordered_groups": [],
    }

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO questions (
                    id, book_ref, test_number, exam_type, skill_area,
                    passage_text, audio_s3_key, answer_key, questions
                )
                VALUES ($1, 'IELTS-test', 1, 'academic', 'listening', '',
                        'exam-audio/IELTS-test/1/section1.mp3', $2::jsonb, $3::jsonb)
                """,
                question_id,
                json.dumps(answer_key),
                json.dumps(questions),
            )

        selected = await QuestionRepository(pool).get_random_unseen_question(
            exam_type="academic",
            skill_area="listening",
            user_id=user_id,
        )

        assert selected is not None, (
            "a Listening test with one nested answer per question was excluded "
            "as incompletely keyed"
        )
        assert selected["id"] == question_id
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_unrelated_null_question_session_does_not_hide_listening_bank() -> None:
    """Writing/speaking sessions may not reference a question-bank row.

    A NULL inside a SQL ``NOT IN`` subquery makes every comparison unknown,
    which previously made a fully servable Listening bank look exhausted for
    any user with one of those sessions.
    """
    pool = await _temporary_question_pool()
    question_id = uuid4()
    user_id = uuid4()
    questions = [
        {
            "number": 1,
            "prompt": "Question 1",
            "question_type": "Sentence Completion",
            "section_number": 1,
        }
    ]
    answer_key = {"answers": {"1": "alpha"}, "unordered_groups": []}

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO questions (
                    id, book_ref, test_number, exam_type, skill_area,
                    passage_text, audio_s3_key, answer_key, questions
                )
                VALUES ($1, 'IELTS-test', 1, 'academic', 'listening', '',
                        'exam-audio/IELTS-test/1/section1.mp3', $2::jsonb, $3::jsonb)
                """,
                question_id,
                json.dumps(answer_key),
                json.dumps(questions),
            )
            await conn.execute(
                """
                INSERT INTO exam_sessions (id, user_id, question_id)
                VALUES ($1, $2, NULL)
                """,
                uuid4(),
                user_id,
            )

        selected = await QuestionRepository(pool).get_random_unseen_question(
            exam_type="academic",
            skill_area="listening",
            user_id=user_id,
        )

        assert selected is not None
        assert selected["id"] == question_id
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_abandoned_attempt_does_not_permanently_consume_a_test() -> None:
    pool = await _temporary_question_pool()
    question_id = uuid4()
    user_id = uuid4()
    questions = [
        {
            "number": 1,
            "prompt": "Question 1",
            "question_type": "Sentence Completion",
            "section_number": 1,
        }
    ]
    answer_key = {"answers": {"1": "alpha"}, "unordered_groups": []}

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO questions (
                    id, book_ref, test_number, exam_type, skill_area,
                    passage_text, audio_s3_key, answer_key, questions
                )
                VALUES ($1, 'IELTS-test', 1, 'academic', 'listening', '',
                        'exam-audio/IELTS-test/1/section1.mp3', $2::jsonb, $3::jsonb)
                """,
                question_id,
                json.dumps(answer_key),
                json.dumps(questions),
            )
            await conn.execute(
                """
                INSERT INTO exam_sessions (id, user_id, question_id, status)
                VALUES ($1, $2, $3, 'abandoned')
                """,
                uuid4(),
                user_id,
                question_id,
            )

        selected = await QuestionRepository(pool).get_random_unseen_question(
            exam_type="academic",
            skill_area="listening",
            user_id=user_id,
        )

        assert selected is not None
        assert selected["id"] == question_id
    finally:
        await pool.close()
