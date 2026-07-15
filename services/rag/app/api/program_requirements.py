from fastapi import APIRouter, HTTPException, Security
import structlog

from app.core.security import verify_api_key
from app.schemas.program_requirements import ProgramRequirementsUpsertRequest
from app.services.program_requirements_service import upsert_program_requirements

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
