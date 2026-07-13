import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from scripts.backfill_local_profiles import run_backfill

@pytest.mark.asyncio
async def test_backfill_failure_isolation():
    # Mock db
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.disconnect = AsyncMock()
    
    # Mock get_all_users generator
    async def mock_get_all_users():
        yield [{"userId": "fail-1"}, {"userId": "success-2"}]
    
    mock_upsert = AsyncMock(side_effect=[Exception("DB timeout"), None])

    with patch("scripts.backfill_local_profiles.db", mock_db), \
         patch("scripts.backfill_local_profiles.get_all_users", mock_get_all_users), \
         patch("scripts.backfill_local_profiles.upsert_local_profiles", mock_upsert):
        
        await run_backfill()
        
    assert mock_upsert.call_count == 2
    args1 = mock_upsert.call_args_list[0][0][0]
    args2 = mock_upsert.call_args_list[1][0][0]
    assert args1["userId"] == "fail-1"
    assert "last_synced_at" in args1
    assert args2["userId"] == "success-2"
    assert "last_synced_at" in args2
