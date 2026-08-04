from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.scoring import ProgramRequirements
from app.services import checklist_financial

client = TestClient(app)

USER_ID = "11111111-1111-1111-1111-111111111111"
PROGRAM_ID = "22222222-2222-2222-2222-222222222222"

PROGRAM = ProgramRequirements(
    id=PROGRAM_ID,
    country="Germany",
    degree_level="Master",
    min_ects=120,
    min_gpa=3.0,
    min_ielts=6.5,
    min_work_experience=0,
    required_citizenship=None,
)

_FINANCE_ITEM = {
    "type": "informational",
    "country": "Germany",
    "issuing_body": "Fintiba",
    "message": "requires proof of 11904 EUR per year via blocked_account",
    "source_url": "https://www.fintiba.com/blocked-account/",
    "last_verified_at": "2026-06-01T00:00:00",
}


# ---------------------------------------------------------------------------
# checklist_financial.get_program_financial_items -- the delegation itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_program_financial_items_returns_none_for_unknown_program(monkeypatch):
    monkeypatch.setattr(
        checklist_financial, "get_program_requirements", AsyncMock(return_value=None)
    )
    result = await checklist_financial.get_program_financial_items(PROGRAM_ID)
    assert result is None


@pytest.mark.asyncio
async def test_get_program_financial_items_returns_empty_when_program_has_no_country(
    monkeypatch,
):
    program_without_country = PROGRAM.model_copy(update={"country": None})
    monkeypatch.setattr(
        checklist_financial,
        "get_program_requirements",
        AsyncMock(return_value=program_without_country),
    )
    finance_mock = AsyncMock()
    monkeypatch.setattr(checklist_financial, "get_student_visa_finance", finance_mock)

    result = await checklist_financial.get_program_financial_items(PROGRAM_ID)

    assert result == []
    finance_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_program_financial_items_delegates_to_visa_finance_by_country(
    monkeypatch,
):
    """Pins the whole point of this module: it calls the existing GOA-108 lookup
    with the program's country and returns its output completely unchanged --
    no reshaping, no LLM, nothing invented."""
    monkeypatch.setattr(
        checklist_financial, "get_program_requirements", AsyncMock(return_value=PROGRAM)
    )
    finance_mock = AsyncMock(return_value=[_FINANCE_ITEM])
    monkeypatch.setattr(checklist_financial, "get_student_visa_finance", finance_mock)

    result = await checklist_financial.get_program_financial_items(PROGRAM_ID)

    finance_mock.assert_awaited_once_with("Germany")
    assert result == [_FINANCE_ITEM]


# ---------------------------------------------------------------------------
# GET /checklists/{program_id}/financial -- API-level header/path validation and
# the response shape the frontend renders from.
# ---------------------------------------------------------------------------


def test_get_financial_missing_user_id_header_returns_422():
    response = client.get(f"/checklists/{PROGRAM_ID}/financial")
    assert response.status_code == 422


def test_get_financial_non_uuid_program_id_returns_404():
    response = client.get(
        "/checklists/not-a-uuid/financial", headers={"X-User-ID": USER_ID}
    )
    assert response.status_code == 404


def test_get_financial_unknown_program_returns_404(monkeypatch):
    monkeypatch.setattr(
        checklist_financial, "get_program_financial_items", AsyncMock(return_value=None)
    )
    response = client.get(
        f"/checklists/{PROGRAM_ID}/financial", headers={"X-User-ID": USER_ID}
    )
    assert response.status_code == 404


def test_get_financial_no_supported_visa_data_returns_empty_items(monkeypatch):
    """GOA-035 AC: omit Financial Requirements if the backend has no supported visa
    data for the program's country -- this is what the frontend keys that off of."""
    monkeypatch.setattr(
        checklist_financial, "get_program_financial_items", AsyncMock(return_value=[])
    )
    response = client.get(
        f"/checklists/{PROGRAM_ID}/financial", headers={"X-User-ID": USER_ID}
    )
    assert response.status_code == 200
    assert response.json() == {"programId": PROGRAM_ID, "items": []}


def test_get_financial_success_preserves_all_structured_fields(monkeypatch):
    monkeypatch.setattr(
        checklist_financial,
        "get_program_financial_items",
        AsyncMock(return_value=[_FINANCE_ITEM]),
    )
    response = client.get(
        f"/checklists/{PROGRAM_ID}/financial", headers={"X-User-ID": USER_ID}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["programId"] == PROGRAM_ID
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["type"] == "informational"
    assert item["country"] == "Germany"
    assert item["issuingBody"] == "Fintiba"
    assert item["message"] == "requires proof of 11904 EUR per year via blocked_account"
    assert item["sourceUrl"] == "https://www.fintiba.com/blocked-account/"
    assert item["lastVerifiedAt"] == "2026-06-01T00:00:00"
