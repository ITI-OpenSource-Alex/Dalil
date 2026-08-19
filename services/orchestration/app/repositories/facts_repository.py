"""Persistence for long-term user facts (GOA-038).

The contradiction rule lives here, and it lives in SQL rather than in Python on
purpose. "A contradicting fact updates the stored value instead of creating a
duplicate" is a statement about a unique index and an ON CONFLICT clause. A
repository that enforced it with a dictionary lookup would pass every test and
guarantee nothing, because a dictionary has no unique index to violate -- which
is exactly how test_heartbeat.py passed 262 lines while the sweep it covered
could not write a single row.

So: tests for this module run against real Postgres. There is no in-memory fake,
deliberately, and adding one would remove the only thing being tested.
"""

from __future__ import annotations

from typing import Literal, Protocol

import structlog
from asyncpg import Pool

from app.schemas.facts import (
    CONTRADICTION_MIN_CONFIDENCE,
    FactCandidate,
    StoredFact,
    normalise,
)

logger = structlog.get_logger("orchestration.facts_repository")

UpsertOutcome = Literal["created", "reinforced", "replaced", "discarded"]


class FactsRepositoryProtocol(Protocol):
    async def get_live_facts(self, user_id: str, ttl_days: int) -> list[StoredFact]: ...

    async def upsert_fact(self, user_id: str, candidate: FactCandidate) -> UpsertOutcome: ...

    async def delete_all_for_user(self, user_id: str) -> int: ...

    async def purge_expired(self, ttl_days: int) -> int: ...


# One statement, so two concurrent sweeps cannot interleave a read and a write.
#
# The WHERE on DO UPDATE is the contradiction rule itself: an incoming value that
# differs from the stored one is only allowed through if it is confident enough.
# Putting it here rather than in Python means it holds for every caller, now and
# later, including a psql session during an incident.
_UPSERT_SQL = """
INSERT INTO user_facts (user_id, fact_type, fact_key, fact_value, confidence, source_session)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (user_id, fact_type, fact_key) DO UPDATE
SET fact_value    = EXCLUDED.fact_value,
    confidence    = GREATEST(user_facts.confidence, EXCLUDED.confidence),
    revision      = user_facts.revision
                    + CASE WHEN EXCLUDED.fact_value = user_facts.fact_value THEN 0 ELSE 1 END,
    extracted_at  = CASE WHEN EXCLUDED.fact_value = user_facts.fact_value
                         THEN user_facts.extracted_at ELSE NOW() END,
    reinforced_at = NOW()
WHERE EXCLUDED.fact_value = user_facts.fact_value
   OR EXCLUDED.confidence >= $7
RETURNING revision
"""

_SELECT_LIVE_SQL = """
SELECT fact_type, fact_key, fact_value, confidence, revision
FROM user_facts
WHERE user_id = $1
  AND reinforced_at > NOW() - ($2::int * INTERVAL '1 day')
ORDER BY fact_type, reinforced_at DESC
"""


class FactsRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def get_live_facts(self, user_id: str, ttl_days: int) -> list[StoredFact]:
        """Every fact for this user that has not expired.

        Expiry is filtered here as well as being purged by the sweep. The filter
        is the correctness mechanism and the purge is housekeeping: a
        purge-only design leaves a fact readable for up to one sweep interval
        past its expiry, and makes the 30-day rule untestable without waiting
        for a sweep to run.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_LIVE_SQL, user_id, ttl_days)
        return [
            StoredFact(
                fact_type=row["fact_type"],
                fact_key=row["fact_key"],
                fact_value=row["fact_value"],
                confidence=row["confidence"],
                revision=row["revision"],
            )
            for row in rows
        ]

    async def upsert_fact(self, user_id: str, candidate: FactCandidate) -> UpsertOutcome:
        """Store a fact, reinforce it, replace it, or refuse it -- see the rule below.

            same value                        -> reinforced (no new row, no revision bump)
            different value, confidence >= .60 -> replaced   (same row, revision + 1)
            different value, confidence <  .60 -> discarded  (nothing written)

        The SELECT below is only used to *label* the outcome for metrics and
        logs. The decision belongs to the SQL: if the statement returns no row,
        the WHERE refused the write, and that is the answer regardless of what
        the label says.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    """
                    SELECT fact_value FROM user_facts
                    WHERE user_id = $1 AND fact_type = $2 AND fact_key = $3
                    FOR UPDATE
                    """,
                    user_id,
                    candidate.fact_type,
                    candidate.fact_key,
                )
                row = await conn.fetchrow(
                    _UPSERT_SQL,
                    user_id,
                    candidate.fact_type,
                    candidate.fact_key,
                    candidate.fact_value,
                    candidate.confidence,
                    candidate.source_session,
                    CONTRADICTION_MIN_CONFIDENCE,
                )

        if row is None:
            # The WHERE blocked it: a contradicting value that was not confident
            # enough to evict what is already stored.
            logger.info(
                "Fact discarded as low-confidence contradiction",
                user_id=user_id,
                fact_type=candidate.fact_type,
                confidence=candidate.confidence,
            )
            return "discarded"

        if existing is None:
            return "created"
        if normalise(existing["fact_value"]) == normalise(candidate.fact_value):
            return "reinforced"
        return "replaced"

    async def delete_all_for_user(self, user_id: str) -> int:
        """Wipe every stored fact for one user. Idempotent; returns rows removed.

        RETURNING, rather than parsing asyncpg's command tag. This number is
        reported back to the user as "we deleted N facts about you", which makes
        it the answer to a privacy question rather than a debug statistic --
        more weight than the last whitespace-separated word of a status string
        should be asked to carry.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "DELETE FROM user_facts WHERE user_id = $1 RETURNING id", user_id
            )
        return len(rows)

    async def purge_expired(self, ttl_days: int) -> int:
        """Housekeeping so the table does not grow without bound.

        Not the mechanism that makes expiry correct -- see get_live_facts.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "DELETE FROM user_facts "
                "WHERE reinforced_at < NOW() - ($1::int * INTERVAL '1 day') "
                "RETURNING id",
                ttl_days,
            )
        return len(rows)
