"""GOA-038 -- fact persistence, against a real database.

There is no in-memory fake here and there must not be one. Every behaviour in
this file is a property of a unique index, a CHECK constraint or an ON CONFLICT
clause; a Python dictionary standing in for the table would satisfy all of it
and prove none of it. That substitution is what let test_heartbeat.py pass 262
lines while the sweep it covered could not write a row.

Running them:
    docker compose up -d postgres
    docker compose run --rm --entrypoint "python -m pytest tests/test_facts_repository.py -v" orchestration

CI already provides Postgres at DATABASE_URL, so these run there unchanged.
"""

import asyncio
import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

from app.repositories.facts_repository import FactsRepository
from app.schemas.facts import FactCandidate, normalise

# asyncio_mode = "auto" (pyproject.toml) already runs the async tests here; a
# module-level asyncio mark would additionally be applied to the two sync ones.
TTL_DAYS = 30


@pytest_asyncio.fixture
async def pool():
    """A real connection pool, with migrations applied.

    Deliberately fails rather than skipping when no database is reachable. A
    skip here would mean the contradiction and duplication rules quietly stop
    being tested, which is the single most load-bearing behaviour in GOA-038.
    """
    dsn = os.environ["DATABASE_URL"]
    try:
        from app.core.database import db

        await db.run_migrations()
        created = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    except Exception as exc:  # noqa: BLE001 - the message is the point
        pytest.fail(
            f"Could not reach Postgres at {dsn!r} ({exc}). These tests need a real "
            "database by design. Start one with `docker compose up -d postgres`."
        )
    try:
        yield created
    finally:
        await created.close()


@pytest_asyncio.fixture
async def repo(pool):
    return FactsRepository(pool)


@pytest.fixture
def user_id():
    """A fresh id per test, so tests never see each other's rows."""
    return f"test-user-{uuid.uuid4()}"


async def count_rows(pool, user_id, fact_type=None) -> int:
    async with pool.acquire() as conn:
        if fact_type:
            return await conn.fetchval(
                "SELECT count(*) FROM user_facts WHERE user_id = $1 AND fact_type = $2",
                user_id,
                fact_type,
            )
        return await conn.fetchval(
            "SELECT count(*) FROM user_facts WHERE user_id = $1", user_id
        )


async def row_for(pool, user_id, fact_type):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM user_facts WHERE user_id = $1 AND fact_type = $2",
            user_id,
            fact_type,
        )


def gpa(value: str, confidence: float = 0.9) -> FactCandidate:
    return FactCandidate(fact_type="gpa", fact_value=value, confidence=confidence)


# ---------------------------------------------------------------- U-01 .. U-06


async def test_u01_insert_creates_one_row(repo, pool, user_id):
    outcome = await repo.upsert_fact(user_id, gpa("3.2"))

    assert outcome == "created"
    assert await count_rows(pool, user_id) == 1
    row = await row_for(pool, user_id, "gpa")
    assert row["fact_value"] == "3.2"
    assert row["revision"] == 1


async def test_u02_same_value_reinforces_without_duplicating(repo, pool, user_id):
    """AC: a repeated fact is reinforcement, not a second fact."""
    await repo.upsert_fact(user_id, gpa("3.2"))
    before = await row_for(pool, user_id, "gpa")

    await asyncio.sleep(0.01)
    outcome = await repo.upsert_fact(user_id, gpa("3.2"))

    assert outcome == "reinforced"
    assert await count_rows(pool, user_id) == 1
    after = await row_for(pool, user_id, "gpa")
    assert after["revision"] == before["revision"], "reinforcement is not a revision"
    assert after["reinforced_at"] > before["reinforced_at"], "expiry clock must restart"
    assert after["extracted_at"] == before["extracted_at"], "the fact is not newly learned"


async def test_u03_contradiction_updates_in_place(repo, pool, user_id):
    """DoD: 'contradicting fact updates to the new value, not a duplicate entry'.

    Asserted with count(*) against the table. A repository return value would
    not distinguish an update from an insert that happened to overwrite.
    """
    await repo.upsert_fact(user_id, gpa("3.2"))
    before = await row_for(pool, user_id, "gpa")

    outcome = await repo.upsert_fact(user_id, gpa("3.6", confidence=0.9))

    assert outcome == "replaced"
    assert await count_rows(pool, user_id) == 1, "a contradiction must not duplicate"
    after = await row_for(pool, user_id, "gpa")
    assert after["fact_value"] == "3.6"
    assert after["revision"] == before["revision"] + 1
    assert after["extracted_at"] > before["extracted_at"]


async def test_u04_low_confidence_contradiction_is_discarded(repo, pool, user_id):
    """A hedged aside must not evict a firmly stated fact."""
    await repo.upsert_fact(
        user_id,
        FactCandidate(fact_type="target_country", fact_value="Germany", confidence=0.95),
    )

    outcome = await repo.upsert_fact(
        user_id,
        FactCandidate(fact_type="target_country", fact_value="Canada", confidence=0.4),
    )

    assert outcome == "discarded"
    assert await count_rows(pool, user_id) == 1
    row = await row_for(pool, user_id, "target_country")
    assert row["fact_value"] == "Germany"
    assert row["revision"] == 1


async def test_u05_multi_valued_type_keeps_distinct_values(repo, pool, user_id):
    """Two mentioned programs are two facts -- the cardinality rule, from the other side."""
    await repo.upsert_fact(
        user_id,
        FactCandidate(
            fact_type="mentioned_program", fact_value="TU Munich Data Science", confidence=0.9
        ),
    )
    await repo.upsert_fact(
        user_id,
        FactCandidate(
            fact_type="mentioned_program", fact_value="RWTH Aachen Robotics", confidence=0.9
        ),
    )

    assert await count_rows(pool, user_id, "mentioned_program") == 2


async def test_u06_multi_valued_type_dedupes_on_normalised_value(repo, pool, user_id):
    for value in ("TU Munich Data Science", "tu munich data science", "  TU Munich Data Science.  "):
        await repo.upsert_fact(
            user_id,
            FactCandidate(fact_type="mentioned_program", fact_value=value, confidence=0.9),
        )

    assert await count_rows(pool, user_id, "mentioned_program") == 1


# ---------------------------------------------------------------- U-07 .. U-09
# The constraints exist so that a bug in the extraction chain cannot become a bad
# row. These tests assert the database refuses, not that Python remembered to check.


async def test_u07_confidence_out_of_range_is_rejected_by_postgres(pool, user_id):
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_facts (user_id, fact_type, fact_value, confidence) "
                "VALUES ($1, 'degree', 'BSc EEE', 7.0)",
                user_id,
            )


async def test_u08_exam_bands_cannot_be_stored_as_facts(pool, user_id):
    """Q1's decision, enforced in the schema.

    Bands are authoritative from the Exam service. A prompt instruction saying
    "never extract IELTS scores" is a request; this constraint is the guarantee
    that a future caller cannot quietly start competing with graded results.
    """
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_facts (user_id, fact_type, fact_value, confidence) "
                "VALUES ($1, 'ielts_band', '7.5', 0.9)",
                user_id,
            )


async def test_u09_oversized_value_is_rejected_by_postgres(pool, user_id):
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_facts (user_id, fact_type, fact_value, confidence) "
                "VALUES ($1, 'concern', $2, 0.9)",
                user_id,
                "x" * 600,
            )


# ---------------------------------------------------------------- U-10 .. U-14


async def backdate(pool, user_id, fact_type, days):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_facts SET reinforced_at = NOW() - ($3::int * INTERVAL '1 day') "
            "WHERE user_id = $1 AND fact_type = $2",
            user_id,
            fact_type,
            days,
        )


async def test_u10_fact_past_ttl_is_not_read_back(repo, pool, user_id):
    await repo.upsert_fact(user_id, gpa("3.2"))
    await backdate(pool, user_id, "gpa", 31)

    assert await repo.get_live_facts(user_id, TTL_DAYS) == []
    assert await count_rows(pool, user_id) == 1, "still on disk -- expiry is a read filter"


async def test_u11_fact_within_ttl_is_read_back(repo, pool, user_id):
    await repo.upsert_fact(user_id, gpa("3.2"))
    await backdate(pool, user_id, "gpa", 29)

    facts = await repo.get_live_facts(user_id, TTL_DAYS)
    assert [f.fact_value for f in facts] == ["3.2"]


async def test_u11b_reinforcement_resets_the_expiry_clock(repo, pool, user_id):
    """'Expire after 30 days without reinforcement' -- the 'without' half."""
    await repo.upsert_fact(user_id, gpa("3.2"))
    await backdate(pool, user_id, "gpa", 29)

    await repo.upsert_fact(user_id, gpa("3.2"))
    await backdate(pool, user_id, "gpa", 5)

    assert len(await repo.get_live_facts(user_id, TTL_DAYS)) == 1


async def test_u12_purge_removes_only_expired_rows(repo, pool, user_id):
    await repo.upsert_fact(user_id, gpa("3.2"))
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="degree", fact_value="BSc EEE", confidence=0.9)
    )
    await backdate(pool, user_id, "gpa", 31)

    await repo.purge_expired(TTL_DAYS)

    assert await count_rows(pool, user_id, "gpa") == 0
    assert await count_rows(pool, user_id, "degree") == 1


async def test_u13_delete_is_scoped_to_one_user(repo, pool, user_id):
    other = f"test-user-{uuid.uuid4()}"
    await repo.upsert_fact(user_id, gpa("3.2"))
    await repo.upsert_fact(
        user_id, FactCandidate(fact_type="degree", fact_value="BSc EEE", confidence=0.9)
    )
    await repo.upsert_fact(other, gpa("3.9"))

    deleted = await repo.delete_all_for_user(user_id)

    assert deleted == 2
    assert await count_rows(pool, user_id) == 0
    assert await count_rows(pool, other) == 1, "one user's erasure is not another's"


async def test_u14_delete_is_idempotent(repo, user_id):
    await repo.upsert_fact(user_id, gpa("3.2"))

    assert await repo.delete_all_for_user(user_id) == 1
    assert await repo.delete_all_for_user(user_id) == 0


# ---------------------------------------------------------------------- U-15


async def test_u15_concurrent_upserts_produce_one_row(repo, pool, user_id):
    """Two sweep workers racing on the same fact.

    Compose runs one replica today, so this is about the design surviving a
    second one rather than about a bug that can be reproduced now. The unique
    index is what makes it safe; this asserts no UniqueViolationError escapes
    and no duplicate lands.
    """
    await asyncio.gather(
        *(repo.upsert_fact(user_id, gpa("3.2", confidence=0.9)) for _ in range(8))
    )

    assert await count_rows(pool, user_id, "gpa") == 1


# ---------------------------------------------------------------------- U-19


def test_u19_normalise_defines_fact_identity():
    assert normalise("  TU  Munich  ") == "tu munich"
    assert normalise("TU Munich.") == "tu munich"
    assert normalise("Germany!") == "germany"
    assert normalise("BSc (Hons)") == "bsc (hons"
    # Not folded: word order and internal punctuation are meaning, not noise.
    assert normalise("MSc Data Science") != normalise("Data Science MSc")


def test_u19b_fact_key_encodes_the_cardinality_rule():
    single = FactCandidate(fact_type="gpa", fact_value="3.2", confidence=0.9)
    multi = FactCandidate(
        fact_type="mentioned_program", fact_value="TU Munich", confidence=0.9
    )

    assert single.fact_key == ""
    assert multi.fact_key == "tu munich"
