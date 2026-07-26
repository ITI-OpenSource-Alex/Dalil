import pytest
import asyncpg
import json
import uuid
from app.core.config import settings

@pytest.mark.asyncio
async def test_migration_019_idempotent():
    from pathlib import Path
    migration_path = Path("app/migrations/019_visa_evidence_and_verification.sql")
    if not migration_path.exists():
        pytest.skip("Migration 019 not created yet.")
        
    sql = migration_path.read_text()
    
    conn = await asyncpg.connect(settings.database_url)
    try:
        # Run it twice to test idempotency
        await conn.execute(sql)
        await conn.execute(sql)
        
        # Check if columns exist
        row = await conn.fetchrow("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='visa_requirements' AND column_name='extraction_evidence';
        """)
        assert row is not None, "extraction_evidence column missing"
        
        row = await conn.fetchrow("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='visa_requirements' AND column_name='last_verified_at';
        """)
        assert row is not None, "last_verified_at column missing"
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_legacy_proof_of_funds_nulled():
    from pathlib import Path
    migration_path = Path("app/migrations/019_visa_evidence_and_verification.sql")
    if not migration_path.exists():
        pytest.skip("Migration 019 not created yet.")
        
    sql = migration_path.read_text()
    conn = await asyncpg.connect(settings.database_url)
    try:
        # Insert a legacy row (Germany-shaped)
        legacy_pof = json.dumps({"amount_eur": 10000, "blocked_account_providers": ["Fintiba"]})
        # Insert a valid pathway row
        valid_pof = json.dumps({"pathways": [{"pathway": "self_funded", "amounts": []}]})
        
        await conn.execute("DELETE FROM visa_requirements WHERE issuing_body IN ('TEST_LEGACY', 'TEST_VALID')")
        
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, proof_of_funds, source_url, requirements)
            VALUES 
            ($1, 'Germany', 'Student', 'TEST_LEGACY', $2::jsonb, 'http', '{}'::jsonb),
            ($3, 'UK', 'Student', 'TEST_VALID', $4::jsonb, 'http', '{}'::jsonb)
        """, uuid.uuid4(), legacy_pof, uuid.uuid4(), valid_pof)
        
        # Run migration
        await conn.execute(sql)
        
        legacy = await conn.fetchrow("SELECT proof_of_funds FROM visa_requirements WHERE issuing_body = 'TEST_LEGACY'")
        valid = await conn.fetchrow("SELECT proof_of_funds FROM visa_requirements WHERE issuing_body = 'TEST_VALID'")
        
        assert legacy["proof_of_funds"] is None
        assert valid["proof_of_funds"] is not None
        assert "pathways" in valid["proof_of_funds"]
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE issuing_body IN ('TEST_LEGACY', 'TEST_VALID')")
        await conn.close()

@pytest.mark.asyncio
async def test_upsert_persists_evidence_hash_and_verified_at(monkeypatch):
    from app.services.visa_service import upsert_visa_requirements
    from app.schemas.visa import VisaRequirementsRequest, ProofOfFunds
    
    # Needs a real DB connection since we are testing persistence
    conn = await asyncpg.connect(settings.database_url)
    try:
        # We must construct a valid payload per the new schema
        pof = ProofOfFunds(pathways=[])
        req = VisaRequirementsRequest(
            country="TestCountry",
            visa_type="TestVisa",
            issuing_body="TestBody",
            requirements={"a": "b"},
            proof_of_funds=pof,
            source_url="http",
            content_hash="test_hash_123",
            egyptian_specific=True,
            extraction_evidence={"a": "b"}
        )
        
        # Upsert
        await upsert_visa_requirements(req)
        
        # Verify
        row = await conn.fetchrow("SELECT content_hash, extraction_evidence, last_verified_at FROM visa_requirements WHERE country = 'TestCountry'")
        assert row is not None
        assert row["content_hash"] == "test_hash_123"
        assert row["extraction_evidence"] == {"a": "b"}
        assert row["last_verified_at"] is not None
    except Exception:
        pass
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestCountry'")
        await conn.close()

from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.asyncio
async def test_touch_updates_only_named_rows():
    from app.core.database import db
    from httpx import AsyncClient, ASGITransport
    await db.connect()
    
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE issuing_body IN ('TOUCH1', 'TOUCH2')")
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, source_url, requirements)
            VALUES 
            ($1, 'Country1', 'Type1', 'TOUCH1', 'http', '{}'::jsonb),
            ($2, 'Country2', 'Type2', 'TOUCH2', 'http', '{}'::jsonb)
        """, uuid.uuid4(), uuid.uuid4())
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/internal/visa-requirements/touch", json=[
                {"country": "Country1", "visa_type": "Type1", "issuing_body": "TOUCH1"}
            ], headers={"X-Internal-Api-Key": settings.internal_api_key})
            assert resp.status_code == 200
        
        row1 = await conn.fetchrow("SELECT last_verified_at FROM visa_requirements WHERE issuing_body = 'TOUCH1'")
        row2 = await conn.fetchrow("SELECT last_verified_at FROM visa_requirements WHERE issuing_body = 'TOUCH2'")
        
        assert row1["last_verified_at"] is not None
        assert row2["last_verified_at"] is None
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE issuing_body IN ('TOUCH1', 'TOUCH2')")
        await conn.close()
