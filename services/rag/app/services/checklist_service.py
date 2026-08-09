from typing import Any

from fastapi import HTTPException, status
from langfuse import observe

from app.schemas.checklists import ChecklistItem, ChecklistResponse
from app.schemas.scoring import ProgramRequirements, UserProfile
from app.services import checklist_repo
from app.services.checklist_generator import build_requirement_checklist
from app.services.gap_report import generate_gap_report
from app.services.scoring import get_local_user_profile, get_program_requirements
from app.services.visa_service import get_visa_requirements_for_country


def _merge_items(
    items: list[dict[str, Any]], states: dict[str, bool]
) -> list[ChecklistItem]:
    return [
        ChecklistItem(
            itemId=item["item_id"],
            title=item["title"],
            description=item.get("description"),
            category=item.get("category"),
            checked=states.get(item["item_id"], False),
        )
        for item in items
    ]


def _to_response(
    checklist: dict[str, Any], states: dict[str, bool]
) -> ChecklistResponse:
    return ChecklistResponse(
        checklistId=str(checklist["id"]),
        programId=str(checklist["program_id"]),
        generatedBy=checklist["generated_by"],
        items=_merge_items(checklist["items"], states),
    )


def _checklist_title(program: ProgramRequirements) -> str:
    parts = [p for p in (program.degree_level, "program in", program.country) if p]
    return (
        f"Application checklist — {' '.join(parts)}"
        if parts
        else "Application checklist"
    )


@observe(as_type="span", name="GOA-084-checklist-get-or-create")
async def get_or_create_checklist(user_id: str, program_id: str) -> ChecklistResponse:
    """Return one checklist row per user/program, refreshing its fact-derived items.

    Stable item ids preserve checked state while profile, programme and visa facts
    change. `uq_checklists_user_program` plus ON CONFLICT keeps concurrent first
    reads from creating duplicate rows.
    """
    program = await get_program_requirements(program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
        )

    profile_dict = await get_local_user_profile(user_id)
    gap_report: dict[str, Any] = {}
    if profile_dict is not None:
        gap_report = generate_gap_report(UserProfile(**profile_dict), program)

    visa_requirements = (
        await get_visa_requirements_for_country(program.country)
        if program.country
        else []
    )
    items = build_requirement_checklist(program, gap_report, visa_requirements)
    generated_by = "requirements"

    existing = await checklist_repo.get_checklist(user_id, program_id)
    if existing is not None:
        refreshed = await checklist_repo.replace_checklist_items(
            existing["id"], items, generated_by
        )
        states = await checklist_repo.get_item_states(existing["id"])
        return _to_response(refreshed, states)

    created = await checklist_repo.create_checklist(
        user_id=user_id,
        program_id=program_id,
        title=_checklist_title(program),
        items=items,
        generated_by=generated_by,
    )
    states = await checklist_repo.get_item_states(created["id"])
    return _to_response(created, states)


@observe(as_type="span", name="GOA-084-checklist-set-item")
async def set_item_checked(
    user_id: str, program_id: str, item_id: str, checked: bool
) -> ChecklistItem:
    checklist = await checklist_repo.get_checklist(user_id, program_id)
    if checklist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found"
        )

    matching = next(
        (item for item in checklist["items"] if item["item_id"] == item_id), None
    )
    if matching is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found"
        )

    await checklist_repo.upsert_item_state(checklist["id"], item_id, checked, user_id)
    return ChecklistItem(
        itemId=matching["item_id"],
        title=matching["title"],
        description=matching.get("description"),
        category=matching.get("category"),
        checked=checked,
    )
