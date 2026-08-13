from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.profile_repo import upsert_local_profiles


@pytest.mark.asyncio
async def test_upsert_local_profiles_mapping(monkeypatch):
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    monkeypatch.setattr("app.core.database.db.pool", mock_pool)

    profile_payload = {
        "userId": "123",
        "ects": 180,
        "gpa": 3.8,
        "gpaScale": "4.0",
        "ieltsScore": 7.5,
        "degreeLevel": "Bachelor",
        "workExperienceYears": 2,
        "extracurricularsScore": 85,
        "targetCountries": ["Germany"],
        "fieldOfStudy": "Computer Science",
        "last_synced_at": "2024-01-01T00:00:00Z",
    }

    await upsert_local_profiles(profile_payload)

    # Verify the database execute method was called
    mock_conn.execute.assert_called_once()
    args = mock_conn.execute.call_args[0]

    # args[0] is the query, args[1:] are the arguments
    assert args[1] == "123"  # user_id
    assert args[2] == 180  # ects
    assert args[3] == 3.8  # gpa
    assert args[4] == "4.0"  # gpaScale (explicit mapping test)
    assert args[5] == 7.5  # ielts
    # Optional IELTS sub-scores: absent keys bind as NULL (older publishers).
    assert args[6] is None  # ielts_listening
    assert args[7] is None  # ielts_reading
    assert args[8] is None  # ielts_writing
    assert args[9] is None  # ielts_speaking
    assert args[10] == "Bachelor"  # degreeLevel
    assert args[11] == 2  # workExp (explicit mapping test)
    assert args[12] == 85  # extracurriculars (explicit mapping test)
    assert args[13] == ["Germany"]  # targetCountries (array mapping test)
    # fieldOfStudy drives match_programs()'s discipline pre-filter. It was absent
    # from both the event payload and this upsert, so field_of_study was NULL for
    # every replicated user and the filter never engaged.
    assert args[14] == "Computer Science"
    assert args[15] == "Computer Science"  # target fallback for older events
    # last_synced_at is parsed, not passed through. This line previously asserted
    # the raw string "2024-01-01T00:00:00Z", pinning the defect in place -- that
    # is precisely the value asyncpg refuses to bind to a timestamptz (BUG-024).
    assert isinstance(args[16], datetime)
    assert args[16] == datetime(2024, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_intended_field_is_replicated_separately_from_bachelors_field(
    monkeypatch,
):
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(
        _payload(
            fieldOfStudy="Mechanical Engineering",
            targetFieldOfStudy="Software Engineering",
        )
    )

    bound = conn.execute.call_args[0]
    assert bound[14] == "Mechanical Engineering"
    assert bound[15] == "Software Engineering"


@pytest.mark.asyncio
async def test_upsert_invalidates_the_cached_match_list(monkeypatch):
    """A profile change must drop match:{user_id}.

    match_programs() caches its ranked list for an hour. Nothing cleared it when
    the profile behind it changed, so a user who fixed their target countries
    kept getting the list computed from the old ones -- an empty result that
    looks exactly like "no programme matches you".
    """
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)
    monkeypatch.setattr("app.core.database.db.pool", mock_pool)

    fake_redis = MagicMock()
    fake_redis.delete = AsyncMock()

    async def _scan(match):  # noqa: ARG001 - signature mirrors redis.scan_iter
        if match.startswith("score:"):
            for key in ("score:123:prog-a", "score:123:prog-b"):
                yield key
        else:
            yield "match:123:requirements-v2"

    fake_redis.scan_iter = _scan
    monkeypatch.setattr("app.services.profile_repo.redis_client.redis", fake_redis)

    await upsert_local_profiles(
        {
            "userId": "123",
            "ects": 180,
            "gpa": 3.8,
            "gpaScale": "4.0",
            "ieltsScore": 7.5,
            "degreeLevel": "Bachelor",
            "workExperienceYears": 2,
            "extracurricularsScore": 85,
            "targetCountries": ["Germany"],
            "fieldOfStudy": "Computer Science",
            "last_synced_at": "2026-08-05T10:00:00Z",
        }
    )

    fake_redis.delete.assert_awaited_once()
    deleted = set(fake_redis.delete.await_args[0])
    assert "match:123" in deleted
    assert "match:123:requirements-v2" in deleted
    assert "score:123:prog-a" in deleted


@pytest.mark.asyncio
async def test_cache_invalidation_failure_does_not_fail_replication(monkeypatch):
    """A Redis outage must not cost the profile update. The stale entry expires;
    a dropped update does not come back."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)
    monkeypatch.setattr("app.core.database.db.pool", mock_pool)

    fake_redis = MagicMock()

    async def _boom(match):  # noqa: ARG001
        raise ConnectionError("redis down")
        yield  # pragma: no cover - makes this an async generator

    fake_redis.scan_iter = _boom
    fake_redis.delete = AsyncMock()
    monkeypatch.setattr("app.services.profile_repo.redis_client.redis", fake_redis)

    await upsert_local_profiles(_payload())

    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_local_profiles_missing_key(monkeypatch):
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    monkeypatch.setattr("app.core.database.db.pool", mock_pool)

    profile_payload = {
        # missing userId
        "ects": 180
    }

    with pytest.raises(KeyError):
        await upsert_local_profiles(profile_payload)


# ---------------------------------------------------------------------------
# Shared fixtures for mapping / timestamp / IELTS sub-score cases
# ---------------------------------------------------------------------------


def _mock_pool(monkeypatch):
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)
    monkeypatch.setattr("app.core.database.db.pool", mock_pool)
    return mock_conn


def _payload(**overrides):
    base = {
        "userId": "123",
        "ects": 180,
        "gpa": 3.8,
        "gpaScale": "4.0",
        "ieltsScore": 7.5,
        "degreeLevel": "Bachelor",
        "workExperienceYears": 2,
        "extracurricularsScore": 85,
        "targetCountries": ["Germany"],
        "fieldOfStudy": "Computer Science",
        "last_synced_at": "2026-07-26T15:32:04.553Z",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GOA-029: IELTS sub-scores replicate into local_user_profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_local_profiles_ielts_subscores_round_trip(monkeypatch):
    """IELTS section bands must land in local_user_profiles, not only overall.

    UserUpdated carries ieltsListening/Reading/Writing/Speaking (GOA-029). Matching
    still scores on ieltsScore alone, but the snapshot has to round-trip the four
    columns so the profile UI / agent can read what the user saved.
    """
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(
        _payload(
            ieltsScore=7.0,
            ieltsListening=7.5,
            ieltsReading=7.0,
            ieltsWriting=6.5,
            ieltsSpeaking=7.0,
        )
    )

    conn.execute.assert_called_once()
    sql, *bound = conn.execute.call_args[0]

    insert_list = sql.split("INSERT INTO local_user_profiles", 1)[1].split(")", 1)[0]
    insert_list = insert_list.split("(", 1)[1]
    columns = [
        c.strip() for c in insert_list.replace("\n", " ").split(",") if c.strip()
    ]

    for column in (
        "ielts_listening",
        "ielts_reading",
        "ielts_writing",
        "ielts_speaking",
    ):
        assert column in columns, f"upsert SQL must include {column}"
        assert f"{column} = EXCLUDED.{column}" in sql

    # Bound $N args follow INSERT column order — that is the round-trip.
    assert bound[columns.index("ielts_listening")] == 7.5
    assert bound[columns.index("ielts_reading")] == 7.0
    assert bound[columns.index("ielts_writing")] == 6.5
    assert bound[columns.index("ielts_speaking")] == 7.0
    assert bound[columns.index("ielts_score")] == 7.0


# ---------------------------------------------------------------------------
# BUG-024: the envelope timestamp must reach asyncpg as a datetime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_js_iso_timestamp_is_bound_as_a_datetime(monkeypatch):
    """The User service stamps events with JavaScript's toISOString(), e.g.
    "2026-07-26T15:32:04.553Z". asyncpg binds timestamptz strictly and rejects a
    str, so every UserUpdated message failed and retried forever -- the profile
    sync had never once succeeded.

    Asserting on the *bound parameter type* is the point. The pre-existing test
    passed this same string happily, because a MagicMock connection accepts
    anything the real driver would refuse.
    """
    from datetime import datetime

    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload())

    # $16 last_synced_at — target_field_of_study precedes it.
    bound = conn.execute.call_args[0][16]
    assert isinstance(bound, datetime), f"expected datetime, got {type(bound).__name__}"
    assert bound.year == 2026 and bound.month == 7 and bound.day == 26
    assert bound.tzinfo is not None, "timestamptz comparisons need an aware datetime"


@pytest.mark.asyncio
async def test_absent_timestamp_stays_none(monkeypatch):
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload(last_synced_at=None))

    assert conn.execute.call_args[0][16] is None


@pytest.mark.asyncio
async def test_malformed_timestamp_does_not_block_the_profile(monkeypatch):
    """A bad timestamp must not cost the user their profile update -- it is
    ordering metadata, not the payload."""
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload(last_synced_at="not-a-timestamp"))

    conn.execute.assert_called_once()
    assert conn.execute.call_args[0][16] is None
