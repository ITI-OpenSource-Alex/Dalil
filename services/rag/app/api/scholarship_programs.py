from fastapi import APIRouter, HTTPException, Security
import structlog

from app.core.security import verify_api_key
from app.schemas.scholarship_programs import ScholarshipProgramUpsertRequest
from app.services.scholarship_programs_service import upsert_scholarship_program

router = APIRouter()
logger = structlog.get_logger("rag_service.api.scholarship_programs")

@router.post("/internal/scholarship-programs")
async def handle_scholarship_programs(request: ScholarshipProgramUpsertRequest, _ = Security(verify_api_key)):
    try:
        data = request.model_dump()
        result = await upsert_scholarship_program(data)
        return result
    except Exception as e:
        logger.error("Scholarship program processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")
