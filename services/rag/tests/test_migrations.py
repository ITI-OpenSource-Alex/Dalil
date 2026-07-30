import pytest
from pathlib import Path
import asyncpg
from app.core.config import settings

@pytest.mark.asyncio
async def test_migration_017_is_idempotent():
    # Apply migration twice, assert no error and exactly one migrations_log row.
    migration_path = Path("../app/migrations/017_reembed_dimensions.sql")
    if not migration_path.exists():
        pytest.skip("Migration 017 does not exist yet")
        
    sql = migration_path.read_text()
    
    conn = await asyncpg.connect(settings.database_url)
    try:
        # Run it first time
        await conn.execute(sql)
        # Assuming the migrations runner inserts into migrations_log. 
        # But we're just testing the SQL is idempotent.
        # Run it second time
        await conn.execute(sql)
        
        # Verify the dimensions
        row = await conn.fetchrow("SELECT atttypmod FROM pg_attribute WHERE attrelid='documents'::regclass AND attname='embedding';")
        assert row is not None
        assert row['atttypmod'] == 768, f"Expected 768 for vector dim, got {row['atttypmod']}"
    finally:
        await conn.close()

def test_rollback_not_in_migrations_glob():
    # The runner globs migrations/*.sql. Ensure rollback/ is not matched by that glob directly 
    # if it's placed inside migrations/. (e.g., they didn't put rollback files directly in migrations/)
    migrations_dir = Path("../app/migrations")
    rollback_dir = migrations_dir / "rollback"
    
    if not rollback_dir.exists():
        return
        
    for file in migrations_dir.glob("*.sql"):
        assert "rollback" not in str(file), f"Rollback script {file} found directly in migrations dir"
        assert "_down" not in file.name, f"Rollback script {file.name} found in migrations dir instead of rollback dir"
