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

    async def try_abandon(self, session_id: UUID) -> bool:
        """Atomically abandon an attempt only while it is still active."""
        query = """
        UPDATE exam_sessions
        SET status='abandoned'
        WHERE id=$1 AND status IN ('pending', 'in_progress')
        RETURNING id
        """

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, session_id)
            return result is not None

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

    async def try_submit(
        self,
        session_id: UUID,
    ) -> bool:
        query = """
        UPDATE exam_sessions
        SET
            status='submitted',
            submitted_at=NOW()
        WHERE id=$1 AND status='in_progress'
        RETURNING id
        """

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, session_id)
            return result is not None

    async def revert_submission(
        self,
        session_id: UUID,
    ) -> bool:
        """Undo try_submit when the evaluation that followed it failed (GOA-134).

        `try_submit` flips the session to 'submitted' BEFORE the speaking service
        is called. When that call failed -- which the old 15-second holistic
        deadline made the normal case rather than an edge case -- no result row
        was ever written, and the guard at the top of the endpoint
        (`status in ("submitted", "scored")`) then returned `{}` for every retry.
        The candidate's exam was silently unrecoverable and the endpoint reported
        success.

        The revert is deliberately narrow: `AND status='submitted'` means a session
        that reached 'scored' in a concurrent request is never dragged backwards.
        Deleting the guard instead would have traded a lost exam for a
        double-graded one.
        """
        query = """
        UPDATE exam_sessions
        SET
            status='in_progress',
            submitted_at=NULL
        WHERE id=$1 AND status='submitted'
        RETURNING id
        """

        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, session_id)
            return result is not None

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
