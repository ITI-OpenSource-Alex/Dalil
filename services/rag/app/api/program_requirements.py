from fastapi import APIRouter, HTTPException, Security
import structlog

from app.core.security import verify_api_key
from app.schemas.program_requirements import ProgramRequirementsUpsertRequest
from app.services.program_requirements_service import upsert_program_requirements
from app.services.scoring import get_program_requirements

router = APIRouter()
logger = structlog.get_logger("rag_service.api.program_requirements")

@router.post("/internal/program-requirements")
async def handle_program_requirements(request: ProgramRequirementsUpsertRequest, _ = Security(verify_api_key)):
    try:
        data = request.model_dump()
        result = await upsert_program_requirements(data)
        return result
    except Exception as e:
        logger.error("Program requirements processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")


@router.get("/internal/programs/{program_id}/requirements")
async def read_program_requirements(program_id: str, _=Security(verify_api_key)):
    """Programme facts for services that need context but must not own the data.

    Writing calls this to give the motivation-letter reviewer something concrete to
    check a letter against. RAG stays authoritative; the caller keeps only the
    snapshot it reviewed against, so a later re-scrape cannot silently rewrite the
    basis of a review that already happened.
    """
    program = await get_program_requirements(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program.model_dump()
