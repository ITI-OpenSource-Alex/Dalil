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
    assert args[10] == "2024-01-01T00:00:00Z" # last_synced_at


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
