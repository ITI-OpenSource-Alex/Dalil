from uuid import UUID

from asyncpg import Pool, Record


class SessionRepository:

    def __init__(self, pool: Pool):
        self.pool = pool

    async def create(
        self,
        session_id: UUID,
        user_id: UUID,
        question_id: UUID,
        exam_type: str,
        skill_area: str,
        status: str,
        time_limit_seconds: int,
    ) -> None:
        query = """
        INSERT INTO exam_sessions(
            id,
            user_id,
            question_id,
            exam_type,
            skill_area,
            status,
            started_at,
            time_limit_seconds
        )
        VALUES(
            $1,$2,$3,$4,$5,$6,NOW(),$7
        )
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                session_id,
                user_id,
                question_id,
                exam_type,
                skill_area,
                status,
                time_limit_seconds,
            )

    async def get_by_id(self, session_id: UUID) -> Record | None:
        query = """
        SELECT *
        FROM exam_sessions
        WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, session_id)

    async def update_status(
        self,
        session_id: UUID,
        status: str,
    ) -> None:
        query = """
        UPDATE exam_sessions
        SET status=$2
        WHERE id=$1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id, status)

    async def submit(
        self,
        session_id: UUID,
    ) -> None:
        query = """
        UPDATE exam_sessions
        SET
            status='submitted',
            submitted_at=NOW()
        WHERE id=$1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id)

    async def mark_scored(
        self,
        session_id: UUID,
    ) -> None:
        query = """
        UPDATE exam_sessions
        SET status='scored'
        WHERE id=$1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id)
