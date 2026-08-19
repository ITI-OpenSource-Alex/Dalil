import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.program_requirements import ProgramRequirementsUpsertRequest
from app.services.program_requirements_service import upsert_program_requirements

client = TestClient(app)

VALID_PAYLOAD = {
    "university": "Technical University Munich",
    "country": "Germany",
    "degree_level": "Master",
    "min_ects": 120,
    "min_gpa": 3.0,
    "min_ielts": 6.5,
    "required_citizenship": None,
    "min_work_experience": 0,
    "source_url": "https://www.mastersportal.com/universities/123/technical-university-munich.html",
    "content_hash": "abc123hash",
}


def test_valid_payload_passes_validation():
    request = ProgramRequirementsUpsertRequest(**VALID_PAYLOAD)
    assert request.university == "Technical University Munich"
    assert request.min_ects == 120


def test_missing_university_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "university"}
    with pytest.raises(ValidationError):
        ProgramRequirementsUpsertRequest(**payload)


def test_missing_country_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "country"}
    with pytest.raises(ValidationError):
        ProgramRequirementsUpsertRequest(**payload)


def test_missing_degree_level_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "degree_level"}
    with pytest.raises(ValidationError):
        ProgramRequirementsUpsertRequest(**payload)


def test_optional_fields_default_to_none():
    request = ProgramRequirementsUpsertRequest(
        university="ETH Zurich", country="Switzerland", degree_level="Master",
        source_url="https://goa.internal/seed/program/eth"
    )
    assert request.min_ects is None
    assert request.required_citizenship is None
    assert request.content_hash is None


def test_model_dump_produces_plain_dict():
    request = ProgramRequirementsUpsertRequest(**VALID_PAYLOAD)
    dumped = request.model_dump()

    assert isinstance(dumped, dict)
    assert dumped["university"] == "Technical University Munich"
    assert dumped["min_ects"] == 120


# ---------------------------------------------------------------------------
# program_requirements_service.upsert_program_requirements -- insert / update
# ---------------------------------------------------------------------------

def make_mock_program_requirements_db(monkeypatch, fetchrow_result):
    """Mirrors test_visa.py's make_mock_visa_db, extended with a transaction()
    context manager since program_requirements_service wraps its writes in one."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_result)

    mock_tx_ctx = MagicMock()
    mock_tx_ctx.__aenter__ = AsyncMock(return_value=None)
    mock_tx_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx_ctx)

    mock_pool_ctx = MagicMock()
    mock_pool_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_pool_ctx)

    monkeypatch.setattr("app.core.database.db.pool", mock_pool)
    return mock_conn


@pytest.mark.asyncio
async def test_upsert_inserts_new_row(monkeypatch):
    new_id = uuid.uuid4()
    # A brand-new row has no conflict, so xmax = 0 -> inserted = True.
    mock_conn = make_mock_program_requirements_db(monkeypatch, {"id": new_id, "inserted": True})

    result = await upsert_program_requirements(VALID_PAYLOAD)

    assert result == {"status": "success", "id": str(new_id), "action": "inserted"}
    assert mock_conn.fetchrow.call_count == 1


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(monkeypatch):
    existing_id = uuid.uuid4()
    # Conflicting row -> DO UPDATE proceeds unconditionally (no content_hash gate),
    # so xmax != 0 -> inserted = False, and last_scraped_at always advances.
    mock_conn = make_mock_program_requirements_db(monkeypatch, {"id": existing_id, "inserted": False})

    result = await upsert_program_requirements(VALID_PAYLOAD)

    assert result == {"status": "success", "id": str(existing_id), "action": "updated"}
    assert mock_conn.fetchrow.call_count == 1


@pytest.mark.asyncio
async def test_upsert_updates_even_with_identical_content_hash(monkeypatch):
    """GOA-088 explicitly requires last_scraped_at to advance on every re-ingestion,
    even when content_hash is unchanged -- unlike the visa pattern, there is no
    suppression branch here, so a repeat call with the same payload still hits
    DO UPDATE (not a no-op)."""
    existing_id = uuid.uuid4()
    mock_conn = make_mock_program_requirements_db(monkeypatch, {"id": existing_id, "inserted": False})

    result = await upsert_program_requirements(VALID_PAYLOAD)

    assert result["action"] == "updated"
    assert mock_conn.fetchrow.call_count == 1


# ---------------------------------------------------------------------------
# POST /internal/program-requirements auth
# ---------------------------------------------------------------------------

def test_program_requirements_endpoint_without_api_key_returns_401():
    response = client.post("/internal/program-requirements", json=VALID_PAYLOAD)
    assert response.status_code == 401


def test_program_requirements_endpoint_with_wrong_api_key_returns_401():
    response = client.post(
        "/internal/program-requirements",
        json=VALID_PAYLOAD,
        headers={"X-Internal-Api-Key": "definitely-the-wrong-key"}
    )
    assert response.status_code == 401


def test_program_requirements_endpoint_with_correct_api_key_succeeds(monkeypatch):
    new_id = uuid.uuid4()
    make_mock_program_requirements_db(monkeypatch, {"id": new_id, "inserted": True})

    response = client.post(
        "/internal/program-requirements",
        json=VALID_PAYLOAD,
        headers={"X-Internal-Api-Key": settings.internal_api_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "inserted"
    assert data["id"] == str(new_id)
