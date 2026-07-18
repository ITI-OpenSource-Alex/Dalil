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
    ) -> None:
        
        query = """
        INSERT INTO exam_speaking_transcripts (session_id, part, transcript_text, duration_s, question_text)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (session_id, part) DO UPDATE SET transcript_text = $3, duration_s = $4, question_text = $5
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id, part, transcript_text, duration_s, question_text)

        

    async def get_all_for_session(self, session_id: UUID) -> list[Record]:

        query = """
        SELECT *
        FROM exam_speaking_transcripts
        WHERE session_id = $1
        ORDER BY part ASC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, session_id)

        