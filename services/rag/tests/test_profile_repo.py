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
        "last_synced_at": "2024-01-01T00:00:00Z"
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
    assert args[6] == "Bachelor"  # degreeLevel
    assert args[7] == 2  # workExp (explicit mapping test)
    assert args[8] == 85  # extracurriculars (explicit mapping test)
    assert args[9] == ["Germany"]  # targetCountries (array mapping test)
    # fieldOfStudy drives match_programs()'s discipline pre-filter. It was absent
    # from both the event payload and this upsert, so field_of_study was NULL for
    # every replicated user and the filter never engaged.
    assert args[10] == "Computer Science"
    # last_synced_at is parsed, not passed through. This line previously asserted
    # the raw string "2024-01-01T00:00:00Z", pinning the defect in place -- that
    # is precisely the value asyncpg refuses to bind to a timestamptz (BUG-024).
    assert isinstance(args[11], datetime)
    assert args[11] == datetime(2024, 1, 1, tzinfo=timezone.utc)


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
        for key in (f"score:123:prog-a", f"score:123:prog-b"):
            yield key

    fake_redis.scan_iter = _scan
    monkeypatch.setattr("app.services.profile_repo.redis_client.redis", fake_redis)

    await upsert_local_profiles({
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
    })

    fake_redis.delete.assert_awaited_once()
    deleted = set(fake_redis.delete.await_args[0])
    assert "match:123" in deleted
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
# BUG-024: the envelope timestamp must reach asyncpg as a datetime
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

    bound = conn.execute.call_args[0][11]
    assert isinstance(bound, datetime), f"expected datetime, got {type(bound).__name__}"
    assert bound.year == 2026 and bound.month == 7 and bound.day == 26
    assert bound.tzinfo is not None, "timestamptz comparisons need an aware datetime"


@pytest.mark.asyncio
async def test_absent_timestamp_stays_none(monkeypatch):
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload(last_synced_at=None))

    assert conn.execute.call_args[0][11] is None


@pytest.mark.asyncio
async def test_malformed_timestamp_does_not_block_the_profile(monkeypatch):
    """A bad timestamp must not cost the user their profile update -- it is
    ordering metadata, not the payload."""
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload(last_synced_at="not-a-timestamp"))

    conn.execute.assert_called_once()
    assert conn.execute.call_args[0][11] is None
