import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.checklists import GeneratedChecklist, GeneratedChecklistItem
from app.schemas.scoring import ProgramRequirements
from app.services import checklist_repo, checklist_service
from app.services.checklist_generator import (
    _normalize_items,
    build_requirement_checklist,
    fallback_checklist,
    generate_checklist,
)

client = TestClient(app)

USER_ID = "11111111-1111-1111-1111-111111111111"
PROGRAM_ID = "22222222-2222-2222-2222-222222222222"

PROGRAM = ProgramRequirements(
    id=PROGRAM_ID,
    name="MSc Computer Science",
    country="Germany",
    discipline="computer_science",
    degree_level="Master",
    min_ects=120,
    min_gpa=3.0,
    min_ielts=6.5,
    min_work_experience=0,
    required_citizenship=None,
)


def _stub_item(item_id="ielts_retake", checked=False):
    return {
        "item_id": item_id,
        "title": "Retake IELTS",
        "description": "Score is below the program minimum.",
        "category": "language",
    }


# ---------------------------------------------------------------------------
# API-level header / path validation
# ---------------------------------------------------------------------------


def test_get_checklist_missing_user_id_header_returns_422():
    response = client.get(f"/checklists/{PROGRAM_ID}")
    assert response.status_code == 422


def test_get_checklist_non_uuid_user_id_returns_422():
    response = client.get(
        f"/checklists/{PROGRAM_ID}", headers={"X-User-ID": "not-a-uuid"}
    )
    assert response.status_code == 422


def test_get_checklist_non_uuid_program_id_returns_404(monkeypatch):
    monkeypatch.setattr(
        checklist_service, "get_program_requirements", AsyncMock(return_value=PROGRAM)
    )
    response = client.get(
        "/checklists/not-a-uuid", headers={"X-User-ID": USER_ID}
    )
    assert response.status_code == 404


def test_get_checklist_unknown_program_returns_404(monkeypatch):
    monkeypatch.setattr(
        checklist_service, "get_program_requirements", AsyncMock(return_value=None)
    )
    response = client.get(
        f"/checklists/{PROGRAM_ID}", headers={"X-User-ID": USER_ID}
    )
    assert response.status_code == 404


def test_put_missing_body_returns_422():
    response = client.put(
        f"/checklists/{PROGRAM_ID}/items/ielts_retake",
        json={},
        headers={"X-User-ID": USER_ID},
    )
    assert response.status_code == 422


def test_put_non_bool_checked_returns_422():
    # Pydantic v2's lax bool parsing accepts "yes"/"no"/"1"/"0"/etc, so this must be
    # a string outside that coercion set to actually exercise the validation error.
    response = client.put(
        f"/checklists/{PROGRAM_ID}/items/ielts_retake",
        json={"checked": "definitely-not-a-boolean"},
        headers={"X-User-ID": USER_ID},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# checklist_service.get_or_create_checklist -- the ticket's central requirement:
# an existing checklist must be returned without ever invoking the generator.
# ---------------------------------------------------------------------------


def _wire_existing_checklist(monkeypatch, checklist_id="33333333-3333-3333-3333-333333333333"):
    monkeypatch.setattr(
        checklist_service, "get_program_requirements", AsyncMock(return_value=PROGRAM)
    )
    monkeypatch.setattr(
        checklist_repo,
        "get_checklist",
        AsyncMock(
            return_value={
                "id": checklist_id,
                "program_id": PROGRAM_ID,
                "items": [_stub_item()],
                "generated_by": "llm",
            }
        ),
    )
    monkeypatch.setattr(
        checklist_repo, "get_item_states", AsyncMock(return_value={"valid_passport": True})
    )
    monkeypatch.setattr(checklist_service, "get_local_user_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(checklist_service, "get_visa_requirements_for_country", AsyncMock(return_value=[]))
    replace_mock = AsyncMock(side_effect=lambda checklist_id, items, generated_by: {
        "id": checklist_id, "program_id": PROGRAM_ID, "items": items, "generated_by": generated_by
    })
    monkeypatch.setattr(checklist_repo, "replace_checklist_items", replace_mock)
    create_mock = AsyncMock()
    monkeypatch.setattr(checklist_repo, "create_checklist", create_mock)
    return replace_mock, create_mock


def test_get_checklist_existing_refreshes_facts_and_preserves_stable_state(monkeypatch):
    replace_mock, create_mock = _wire_existing_checklist(monkeypatch)

    response = client.get(f"/checklists/{PROGRAM_ID}", headers={"X-User-ID": USER_ID})

    assert response.status_code == 200
    data = response.json()
    assert data["checklistId"] == "33333333-3333-3333-3333-333333333333"
    assert data["programName"] == "MSc Computer Science"
    assert data["country"] == "Germany"
    assert data["discipline"] == "computer_science"
    assert data["generatedBy"] == "requirements"
    assert data["items"][0]["itemId"] == "valid_passport"
    assert data["items"][0]["checked"] is True
    replace_mock.assert_awaited_once()
    create_mock.assert_not_awaited()


def test_get_checklist_generates_and_persists_when_absent(monkeypatch):
    monkeypatch.setattr(
        checklist_service, "get_program_requirements", AsyncMock(return_value=PROGRAM)
    )
    monkeypatch.setattr(checklist_repo, "get_checklist", AsyncMock(return_value=None))
    monkeypatch.setattr(
        checklist_service, "get_local_user_profile", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(checklist_service, "get_visa_requirements_for_country", AsyncMock(return_value=[]))
    create_mock = AsyncMock(side_effect=lambda **kwargs: {
        "id": "44444444-4444-4444-4444-444444444444", "program_id": PROGRAM_ID,
        "items": kwargs["items"], "generated_by": kwargs["generated_by"]
    })
    monkeypatch.setattr(checklist_repo, "create_checklist", create_mock)
    monkeypatch.setattr(checklist_repo, "get_item_states", AsyncMock(return_value={}))

    response = client.get(f"/checklists/{PROGRAM_ID}", headers={"X-User-ID": USER_ID})

    assert response.status_code == 200
    data = response.json()
    assert data["checklistId"] == "44444444-4444-4444-4444-444444444444"
    assert data["items"][0]["checked"] is False
    create_mock.assert_awaited_once()
    assert create_mock.call_args.kwargs["generated_by"] == "requirements"
    assert data["items"][0]["itemId"] == "valid_passport"


def test_get_checklist_without_profile_still_uses_program_requirements(monkeypatch):
    """No local_user_profiles row must not block generation -- it's a valid state
    for a user who hasn't synced a profile yet, not an error."""
    monkeypatch.setattr(
        checklist_service, "get_program_requirements", AsyncMock(return_value=PROGRAM)
    )
    monkeypatch.setattr(checklist_repo, "get_checklist", AsyncMock(return_value=None))
    monkeypatch.setattr(
        checklist_service, "get_local_user_profile", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(checklist_service, "get_visa_requirements_for_country", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        checklist_repo,
        "create_checklist",
        AsyncMock(
            return_value={
                "id": "55555555-5555-5555-5555-555555555555",
                "program_id": PROGRAM_ID,
                "items": [{"item_id": "valid_passport", "title": "Valid passport", "description": None, "category": "documents"}],
                "generated_by": "requirements",
            }
        ),
    )
    monkeypatch.setattr(checklist_repo, "get_item_states", AsyncMock(return_value={}))

    response = client.get(f"/checklists/{PROGRAM_ID}", headers={"X-User-ID": USER_ID})

    assert response.status_code == 200
    assert response.json()["generatedBy"] == "requirements"


# ---------------------------------------------------------------------------
# checklist_service.set_item_checked
# ---------------------------------------------------------------------------


def test_put_item_not_found_returns_404(monkeypatch):
    monkeypatch.setattr(
        checklist_repo,
        "get_checklist",
        AsyncMock(
            return_value={
                "id": "33333333-3333-3333-3333-333333333333",
                "program_id": PROGRAM_ID,
                "items": [_stub_item()],
                "generated_by": "llm",
            }
        ),
    )
    response = client.put(
        f"/checklists/{PROGRAM_ID}/items/unknown_item",
        json={"checked": True},
        headers={"X-User-ID": USER_ID},
    )
    assert response.status_code == 404


def test_put_no_checklist_returns_404(monkeypatch):
    monkeypatch.setattr(checklist_repo, "get_checklist", AsyncMock(return_value=None))
    response = client.put(
        f"/checklists/{PROGRAM_ID}/items/ielts_retake",
        json={"checked": True},
        headers={"X-User-ID": USER_ID},
    )
    assert response.status_code == 404


def test_put_success_updates_state(monkeypatch):
    monkeypatch.setattr(
        checklist_repo,
        "get_checklist",
        AsyncMock(
            return_value={
                "id": "33333333-3333-3333-3333-333333333333",
                "program_id": PROGRAM_ID,
                "items": [_stub_item()],
                "generated_by": "llm",
            }
        ),
    )
    upsert_mock = AsyncMock()
    monkeypatch.setattr(checklist_repo, "upsert_item_state", upsert_mock)

    response = client.put(
        f"/checklists/{PROGRAM_ID}/items/ielts_retake",
        json={"checked": True},
        headers={"X-User-ID": USER_ID},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["itemId"] == "ielts_retake"
    assert data["checked"] is True
    upsert_mock.assert_awaited_once_with(
        "33333333-3333-3333-3333-333333333333", "ielts_retake", True, USER_ID
    )


# ---------------------------------------------------------------------------
# checklist_generator
# ---------------------------------------------------------------------------


def test_normalize_items_dedupes_slugs_and_truncates():
    items = [
        GeneratedChecklistItem(item_id="IELTS Retake!", title="A" * 300, description="d", category="c"),
        GeneratedChecklistItem(item_id="ielts_retake", title="dup", description=None, category=None),
    ]
    normalized = _normalize_items(items)
    ids = [i["item_id"] for i in normalized]
    assert ids == ["ielts_retake", "ielts_retake_2"]
    assert len(normalized[0]["title"]) == 255


def test_normalize_items_caps_at_max_items():
    items = [
        GeneratedChecklistItem(item_id=f"item_{i}", title=f"Item {i}")
        for i in range(20)
    ]
    normalized = _normalize_items(items)
    assert len(normalized) == 15


def test_fallback_checklist_is_non_empty_and_normalized():
    items = fallback_checklist()
    assert len(items) >= 5
    ids = [i["item_id"] for i in items]
    assert len(ids) == len(set(ids))


def test_requirement_checklist_contains_program_papers_profile_gaps_and_visa():
    items = build_requirement_checklist(
        PROGRAM,
        {"ielts": {"message": "IELTS 6.0 is below required 6.5."}},
        [{"visa_type": "Student visa", "issuing_body": "Embassy", "requirements": {"photo": True}, "source_url": "https://example.test/visa"}],
    )
    ids = {item["item_id"] for item in items}
    assert {"academic_transcripts", "degree_certificate", "ielts_certificate", "gap_ielts", "visa_documents_1"} <= ids


def _mock_chat_anthropic(monkeypatch, ainvoke_result=None, ainvoke_side_effect=None):
    """ChatAnthropic(...).with_structured_output(...) returns an object whose
    .ainvoke(...) is awaited -- the mock must reproduce that exact shape, rather than
    stubbing with_structured_output's return value itself as the awaitable, or
    structured_llm.ainvoke(prompt) silently resolves to an unrelated auto-mock."""
    structured_llm = MagicMock()
    if ainvoke_side_effect is not None:
        structured_llm.ainvoke = AsyncMock(side_effect=ainvoke_side_effect)
    else:
        structured_llm.ainvoke = AsyncMock(return_value=ainvoke_result)

    llm_instance = MagicMock()
    llm_instance.with_structured_output = MagicMock(return_value=structured_llm)
    monkeypatch.setattr(
        "app.services.checklist_generator.ChatAnthropic",
        MagicMock(return_value=llm_instance),
    )
    return structured_llm


@pytest.mark.asyncio
async def test_generate_checklist_returns_llm_items_on_success(monkeypatch):
    parsed = GeneratedChecklist(
        items=[GeneratedChecklistItem(item_id="passport", title="Get passport")]
    )
    mock_raw = MagicMock()
    mock_raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    _mock_chat_anthropic(monkeypatch, ainvoke_result={"parsed": parsed, "raw": mock_raw})

    items, generated_by = await generate_checklist("user-1", PROGRAM, None, {})

    assert generated_by == "llm"
    assert items == [
        {"item_id": "passport", "title": "Get passport", "description": None, "category": None}
    ]


@pytest.mark.asyncio
async def test_generate_checklist_falls_back_on_llm_exception(monkeypatch):
    _mock_chat_anthropic(monkeypatch, ainvoke_side_effect=RuntimeError("gateway timeout"))

    items, generated_by = await generate_checklist("user-1", PROGRAM, None, {})

    assert generated_by == "fallback"
    assert items == fallback_checklist()


@pytest.mark.asyncio
async def test_generate_checklist_falls_back_on_empty_llm_output(monkeypatch):
    parsed = GeneratedChecklist(items=[])
    _mock_chat_anthropic(
        monkeypatch,
        ainvoke_result={"parsed": parsed, "raw": MagicMock(response_metadata={})},
    )

    items, generated_by = await generate_checklist("user-1", PROGRAM, None, {})

    assert generated_by == "fallback"


@pytest.mark.asyncio
async def test_generate_checklist_falls_back_on_none_parsed(monkeypatch):
    """langchain's with_structured_output(include_raw=True) sets parsed=None on a
    schema-validation failure rather than raising -- must degrade the same way."""
    _mock_chat_anthropic(
        monkeypatch,
        ainvoke_result={"parsed": None, "raw": MagicMock(response_metadata={})},
    )

    items, generated_by = await generate_checklist("user-1", PROGRAM, None, {})

    assert generated_by == "fallback"


# ---------------------------------------------------------------------------
# checklist_repo -- JSONB decoding and race-safe create
# ---------------------------------------------------------------------------


def _mock_pool_ctx(monkeypatch, mock_conn):
    mock_pool = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)
    monkeypatch.setattr("app.core.database.db.pool", mock_pool)


@pytest.mark.asyncio
async def test_get_checklist_decodes_jsonb_string(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(
        return_value={
            "id": uuid.uuid4(),
            "program_id": PROGRAM_ID,
            "items": '[{"item_id": "passport", "title": "Get passport", "description": null, "category": null}]',
            "generated_by": "llm",
        }
    )
    _mock_pool_ctx(monkeypatch, mock_conn)

    result = await checklist_repo.get_checklist(USER_ID, PROGRAM_ID)

    assert isinstance(result["items"], list)
    assert result["items"][0]["item_id"] == "passport"


@pytest.mark.asyncio
async def test_get_checklist_returns_none_when_absent(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    _mock_pool_ctx(monkeypatch, mock_conn)

    result = await checklist_repo.get_checklist(USER_ID, PROGRAM_ID)
    assert result is None


@pytest.mark.asyncio
async def test_create_checklist_falls_back_to_reselect_on_conflict(monkeypatch):
    """Simulates the race: this call's INSERT ... ON CONFLICT DO NOTHING loses,
    so it must return the winner's row via the re-select, not raise or return None."""
    mock_conn = AsyncMock()
    winner_row = {
        "id": uuid.uuid4(),
        "program_id": PROGRAM_ID,
        "items": "[]",
        "generated_by": "llm",
    }
    mock_conn.fetchrow = AsyncMock(side_effect=[None, winner_row])
    mock_tx_ctx = MagicMock()
    mock_tx_ctx.__aenter__ = AsyncMock(return_value=None)
    mock_tx_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx_ctx)
    _mock_pool_ctx(monkeypatch, mock_conn)

    result = await checklist_repo.create_checklist(
        USER_ID, PROGRAM_ID, "Title", [], "llm"
    )

    assert result["items"] == []
    assert mock_conn.fetchrow.call_count == 2
