import uuid
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.scholarship_programs import ScholarshipProgramUpsertRequest
from app.services.scholarship_programs_service import upsert_scholarship_program

client = TestClient(app)

VALID_PAYLOAD = {
    "name": "Chevening Scholarship",
    "provider": "Chevening",
    "source_url": "https://www.chevening.org/scholarships/who-can-apply/",
    "country": "UK",
    "degree_level": "Master",
    "award_amount": "Full tuition, monthly stipend, economy return airfare",
    "deadline": "2026-11-03",
    "eligibility": {"items": ["Egyptian citizenship", "2+ years work experience"]},
    "citizenship_eligible": True,
    "min_gpa": 3.0,
    "min_ielts": 6.5,
    "content_hash": "def456hash",
}


def test_valid_payload_passes_validation():
    request = ScholarshipProgramUpsertRequest(**VALID_PAYLOAD)
    assert request.provider == "Chevening"
    assert request.deadline == date(2026, 11, 3)


def test_missing_name_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "name"}
    with pytest.raises(ValidationError):
        ScholarshipProgramUpsertRequest(**payload)


def test_missing_provider_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "provider"}
    with pytest.raises(ValidationError):
        ScholarshipProgramUpsertRequest(**payload)


def test_missing_source_url_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "source_url"}
    with pytest.raises(ValidationError):
        ScholarshipProgramUpsertRequest(**payload)


def test_unparseable_deadline_coerces_to_none_instead_of_raising():
    payload = dict(VALID_PAYLOAD)
    payload["deadline"] = "rolling / check individual programme page"
    request = ScholarshipProgramUpsertRequest(**payload)
    assert request.deadline is None


def test_missing_deadline_defaults_to_none():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "deadline"}
    request = ScholarshipProgramUpsertRequest(**payload)
    assert request.deadline is None


def test_eligibility_defaults_to_empty_dict():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "eligibility"}
    request = ScholarshipProgramUpsertRequest(**payload)
    assert request.eligibility == {}


def test_citizenship_eligible_defaults_to_true():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "citizenship_eligible"}
    request = ScholarshipProgramUpsertRequest(**payload)
    assert request.citizenship_eligible is True


def test_model_dump_produces_plain_dict():
    request = ScholarshipProgramUpsertRequest(**VALID_PAYLOAD)
    dumped = request.model_dump()

    assert isinstance(dumped, dict)
    assert dumped["provider"] == "Chevening"
    assert isinstance(dumped["eligibility"], dict)


# ---------------------------------------------------------------------------
# scholarship_programs_service.upsert_scholarship_program -- insert / update
# ---------------------------------------------------------------------------

def make_mock_scholarship_programs_db(monkeypatch, fetchrow_result):
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
    mock_conn = make_mock_scholarship_programs_db(monkeypatch, {"id": new_id, "inserted": True})

    data = ScholarshipProgramUpsertRequest(**VALID_PAYLOAD).model_dump()
    result = await upsert_scholarship_program(data)

    assert result == {"status": "success", "id": str(new_id), "action": "inserted"}
    assert mock_conn.fetchrow.call_count == 1


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(monkeypatch):
    existing_id = uuid.uuid4()
    mock_conn = make_mock_scholarship_programs_db(monkeypatch, {"id": existing_id, "inserted": False})

    data = ScholarshipProgramUpsertRequest(**VALID_PAYLOAD).model_dump()
    result = await upsert_scholarship_program(data)

    assert result == {"status": "success", "id": str(existing_id), "action": "updated"}
    assert mock_conn.fetchrow.call_count == 1


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_still_advances_last_scraped_at(monkeypatch):
    """Re-running the exact same payload must not error and must always go through
    DO UPDATE (never suppressed), matching GOA-088's explicit acceptance criterion
    that last_scraped_at is updated on every re-post, not just on real changes."""
    existing_id = uuid.uuid4()
    mock_conn = make_mock_scholarship_programs_db(monkeypatch, {"id": existing_id, "inserted": False})

    data = ScholarshipProgramUpsertRequest(**VALID_PAYLOAD).model_dump()
    first = await upsert_scholarship_program(data)
    second = await upsert_scholarship_program(data)

    assert first["id"] == second["id"] == str(existing_id)
    assert first["action"] == second["action"] == "updated"
    assert mock_conn.fetchrow.call_count == 2


# ---------------------------------------------------------------------------
# POST /internal/scholarship-programs auth
# ---------------------------------------------------------------------------

def test_scholarship_programs_endpoint_without_api_key_returns_401():
    response = client.post("/internal/scholarship-programs", json=VALID_PAYLOAD)
    assert response.status_code == 401


def test_scholarship_programs_endpoint_with_wrong_api_key_returns_401():
    response = client.post(
        "/internal/scholarship-programs",
        json=VALID_PAYLOAD,
        headers={"X-Internal-Api-Key": "definitely-the-wrong-key"}
    )
    assert response.status_code == 401


def test_scholarship_programs_endpoint_with_correct_api_key_succeeds(monkeypatch):
    new_id = uuid.uuid4()
    make_mock_scholarship_programs_db(monkeypatch, {"id": new_id, "inserted": True})

    response = client.post(
        "/internal/scholarship-programs",
        json=VALID_PAYLOAD,
        headers={"X-Internal-Api-Key": settings.internal_api_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "inserted"
    assert data["id"] == str(new_id)
