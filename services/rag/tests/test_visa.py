import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.visa import VisaRequirementsRequest
from app.services.visa_service import upsert_visa_requirements

client = TestClient(app)

VALID_PAYLOAD = {
    "country": "Germany",
    "visa_type": "Student",
    "issuing_body": "German Embassy Cairo",
    "requirements": {"passport": True, "funds_eur": 11208},
    "proof_of_funds": {
        "pathways": [
            {
                "pathway": "blocked_account",
                "amounts": [{"amount": 11208.0, "currency": "EUR", "period": "per_year"}],
                "notes": "EGP transfers must be converted to EUR before deposit."
            }
        ]
    },
    "source_url": "https://germany.info",
    "processing_days_min": 30,
    "processing_days_max": 90,
    "notes": "Bring physical biometric photos.",
    "content_hash": "abc123hash",
    "egyptian_specific": True
}


def test_valid_payload_passes_validation():
    request = VisaRequirementsRequest(**VALID_PAYLOAD)
    assert request.egyptian_specific is True
    assert request.proof_of_funds.pathways[0].amounts[0].amount == 11208.0
    assert request.proof_of_funds.pathways[0].pathway == "blocked_account"


def test_missing_egyptian_specific_raises_validation_error():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "egyptian_specific"}
    with pytest.raises(ValidationError):
        VisaRequirementsRequest(**payload)


def test_malformed_proof_of_funds_amount_raises_validation_error():
    payload = dict(VALID_PAYLOAD)
    payload["proof_of_funds"] = {"pathways": "not-a-list"}
    with pytest.raises(ValidationError):
        VisaRequirementsRequest(**payload)


def test_model_dump_produces_plain_nested_dict():
    request = VisaRequirementsRequest(**VALID_PAYLOAD)
    dumped = request.model_dump()

    assert isinstance(dumped, dict)
    assert dumped["egyptian_specific"] is True
    assert isinstance(dumped["proof_of_funds"], dict)
    assert dumped["proof_of_funds"]["pathways"][0]["amounts"][0]["amount"] == 11208.0
    assert dumped["proof_of_funds"]["pathways"][0]["pathway"] == "blocked_account"


# ---------------------------------------------------------------------------
# Task 03: visa_service.upsert_visa_requirements — insert / update / unchanged
# ---------------------------------------------------------------------------

def make_mock_visa_db(monkeypatch, fetchrow_results=None):
    """Helper mirroring test_query.py's make_mock_db_pool, extended with a
    transaction() context manager since visa_service wraps its writes in one."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_results)
    mock_conn.execute = AsyncMock(return_value=None)

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
    # Single atomic INSERT ... ON CONFLICT ... RETURNING id, (xmax = 0) AS inserted.
    # A brand-new row has no conflict, so xmax = 0 -> inserted = True.
    mock_conn = make_mock_visa_db(monkeypatch, fetchrow_results=[{"id": new_id, "inserted": True}])

    result = await upsert_visa_requirements(VALID_PAYLOAD)

    assert result == {"status": "success", "id": str(new_id), "action": "inserted"}
    assert mock_conn.fetchrow.call_count == 1
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_is_unchanged_when_content_hash_matches(monkeypatch):
    existing_id = uuid.uuid4()
    # The DO UPDATE's WHERE clause suppresses the update when content_hash is
    # unchanged, so RETURNING yields no row (None) -- the code falls back to a plain
    # SELECT to report the existing row's id.
    mock_conn = make_mock_visa_db(
        monkeypatch,
        fetchrow_results=[None, {"id": existing_id}],
    )

    result = await upsert_visa_requirements(VALID_PAYLOAD)

    assert result == {"status": "success", "id": str(existing_id), "action": "unchanged"}
    assert mock_conn.fetchrow.call_count == 2
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_updates_when_content_hash_differs(monkeypatch):
    existing_id = uuid.uuid4()
    # Conflicting row, content_hash differs -> DO UPDATE proceeds; the updated tuple
    # is not a fresh insert, so xmax != 0 -> inserted = False.
    mock_conn = make_mock_visa_db(
        monkeypatch,
        fetchrow_results=[{"id": existing_id, "inserted": False}],
    )

    result = await upsert_visa_requirements(VALID_PAYLOAD)

    assert result == {"status": "success", "id": str(existing_id), "action": "updated"}
    assert mock_conn.fetchrow.call_count == 1
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_treats_matching_none_content_hash_as_unchanged(monkeypatch):
    existing_id = uuid.uuid4()
    mock_conn = make_mock_visa_db(
        monkeypatch,
        fetchrow_results=[None, {"id": existing_id}],
    )
    payload = dict(VALID_PAYLOAD)
    payload["content_hash"] = None

    result = await upsert_visa_requirements(payload)

    assert result["action"] == "unchanged"
    mock_conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Task 04: POST /internal/visa-requirements auth
# ---------------------------------------------------------------------------

def test_visa_endpoint_without_api_key_returns_401():
    response = client.post("/internal/visa-requirements", json=VALID_PAYLOAD)
    assert response.status_code == 401


def test_visa_endpoint_with_wrong_api_key_returns_401():
    response = client.post(
        "/internal/visa-requirements",
        json=VALID_PAYLOAD,
        headers={"X-Internal-Api-Key": "definitely-the-wrong-key"}
    )
    assert response.status_code == 401


def test_visa_endpoint_with_correct_api_key_succeeds(monkeypatch):
    new_id = uuid.uuid4()
    make_mock_visa_db(monkeypatch, fetchrow_results=[{"id": new_id, "inserted": True}])

    response = client.post(
        "/internal/visa-requirements",
        json=VALID_PAYLOAD,
        headers={"X-Internal-Api-Key": settings.internal_api_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "inserted"
    assert data["id"] == str(new_id)


def test_documents_endpoint_auth_still_enforced_after_extraction(monkeypatch):
    """Regression check for Task 04's shared-module extraction: /internal/documents
    must still require the same header after verify_api_key moved to app.core.security."""
    response = client.post("/internal/documents", json={"documents": []})
    assert response.status_code == 401
