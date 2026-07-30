from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_user_id
from app.schemas.checklists import ChecklistItem, ChecklistItemStateUpdate, ChecklistResponse
from app.services import checklist_service

router = APIRouter(prefix="/checklists", tags=["checklists"])
logger = structlog.get_logger("rag_service.api.checklists")


def _validate_program_id(program_id: str) -> str:
    """A malformed program_id can never match a row in program_requirements (a UUID
    PK), so treat it the same as "no such program" rather than letting an invalid
    UUID literal reach asyncpg and surface as an unhandled 500."""
    try:
        UUID(program_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return program_id


@router.get("/{program_id}", response_model=ChecklistResponse)
async def get_checklist(program_id: str, user_id: str = Depends(require_user_id)):
    program_id = _validate_program_id(program_id)
    return await checklist_service.get_or_create_checklist(user_id, program_id)


@router.put("/{program_id}/items/{item_id}", response_model=ChecklistItem)
async def update_checklist_item(
    program_id: str,
    item_id: str,
    request: ChecklistItemStateUpdate,
    user_id: str = Depends(require_user_id),
):
    program_id = _validate_program_id(program_id)
    return await checklist_service.set_item_checked(
        user_id, program_id, item_id, request.checked
    )
