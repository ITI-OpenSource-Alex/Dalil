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
    # last_synced_at is parsed, not passed through. This line previously asserted
    # the raw string "2024-01-01T00:00:00Z", pinning the defect in place -- that
    # is precisely the value asyncpg refuses to bind to a timestamptz (BUG-024).
    assert isinstance(args[10], datetime)
    assert args[10] == datetime(2024, 1, 1, tzinfo=timezone.utc)


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

    bound = conn.execute.call_args[0][10]
    assert isinstance(bound, datetime), f"expected datetime, got {type(bound).__name__}"
    assert bound.year == 2026 and bound.month == 7 and bound.day == 26
    assert bound.tzinfo is not None, "timestamptz comparisons need an aware datetime"


@pytest.mark.asyncio
async def test_absent_timestamp_stays_none(monkeypatch):
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload(last_synced_at=None))

    assert conn.execute.call_args[0][10] is None


@pytest.mark.asyncio
async def test_malformed_timestamp_does_not_block_the_profile(monkeypatch):
    """A bad timestamp must not cost the user their profile update -- it is
    ordering metadata, not the payload."""
    conn = _mock_pool(monkeypatch)

    await upsert_local_profiles(_payload(last_synced_at="not-a-timestamp"))

    conn.execute.assert_called_once()
    assert conn.execute.call_args[0][10] is None
