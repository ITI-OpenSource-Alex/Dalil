from fastapi import APIRouter, HTTPException
import structlog

from app.schemas.visa import VisaRequirementsRequest
from app.services.visa_service import upsert_visa_requirements

router = APIRouter()
logger = structlog.get_logger("rag_service.api.visa")


@router.post("/internal/visa-requirements")
async def handle_visa_requirements(request: VisaRequirementsRequest):
    try:
        data = request.model_dump()
        result = await upsert_visa_requirements(data)
        return result
    except Exception as e:
        logger.error("Visa requirements processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")
