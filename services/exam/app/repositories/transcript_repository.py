import json
from uuid import UUID
from asyncpg import Pool, Record


class TranscriptRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def create_or_update(
        self,
        session_id: UUID,
        part: int,
        transcript_text: str,
        duration_s: int,
        question_text: str,
        words: list[dict] | None = None,
        audio_duration_s: float | None = None,
    ) -> None:
        """Persist one part's transcript and, since GOA-133, its word timings.

        `words` and `audio_duration_s` are optional so a caller that has not been
        updated keeps working: they store as NULL, and the evaluator then omits
        the measured-feature block rather than rendering zeros.
        """

        query = """
        INSERT INTO exam_speaking_transcripts (
            session_id, part, transcript_text, duration_s, question_text,
            words, audio_duration_s
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        ON CONFLICT (session_id, part) DO UPDATE SET
            transcript_text = $3,
            duration_s = $4,
            question_text = $5,
            -- COALESCE so a re-post WITHOUT timings does not erase timings an
            -- earlier post supplied. Re-submitting a part is an ordinary retry
            -- and must not quietly downgrade the evidence already stored.
            words = COALESCE($6::jsonb, exam_speaking_transcripts.words),
            audio_duration_s = COALESCE($7, exam_speaking_transcripts.audio_duration_s)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                session_id,
                part,
                transcript_text,
                duration_s,
                question_text,
                json.dumps(words) if words is not None else None,
                audio_duration_s,
            )

    async def get_all_for_session(self, session_id: UUID) -> list[Record]:

        query = """
        SELECT *
        FROM exam_speaking_transcripts
        WHERE session_id = $1
        ORDER BY part ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, session_id)
