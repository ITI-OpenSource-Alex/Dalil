from fastapi import APIRouter, HTTPException, Security
import structlog

from app.core.database import db
from app.core.security import verify_api_key
from app.schemas.visa import VisaRequirementsRequest
from app.services.visa_service import upsert_visa_requirements

router = APIRouter()
logger = structlog.get_logger("rag_service.api.visa")


@router.get("/internal/visa-sources")
async def list_visa_sources(_=Security(verify_api_key)):
    """Config list the generic VisaSourceAdapter (GOA-116) crawls.

    The Ingestion service has no database driver — it talks to RAG over internal HTTP —
    so the adapter reads its source list here rather than querying rag_db directly.
    """
    query = """
        SELECT s.id, s.country, s.visa_type, s.issuing_body, s.source_url, s.fetch_method, r.content_hash
        FROM visa_sources s
        LEFT JOIN visa_requirements r ON s.country = r.country AND s.visa_type = r.visa_type AND s.issuing_body = r.issuing_body
        WHERE s.active IS TRUE
        ORDER BY s.country, s.issuing_body
    """
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query)
        # id is a UUID column, so asyncpg returns uuid.UUID — coerce to str or the
        # consumer's Pydantic model (typed str) rejects every row.
        return {
            "sources": [
                {
                    "id": str(r["id"]),
                    "country": r["country"],
                    "visa_type": r["visa_type"],
                    "issuing_body": r["issuing_body"],
                    "source_url": r["source_url"],
                    "fetch_method": r["fetch_method"],
                    "content_hash": r["content_hash"],
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Failed to list visa sources", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")


@router.post("/internal/visa-requirements")
async def handle_visa_requirements(request: VisaRequirementsRequest, _ = Security(verify_api_key)):
    try:
        data = request.model_dump()
        result = await upsert_visa_requirements(data)
        return result
    except Exception as e:
        logger.error("Visa requirements processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")


from pydantic import BaseModel
from typing import List

class TouchRequest(BaseModel):
    country: str
    visa_type: str
    issuing_body: str

@router.post("/internal/visa-requirements/touch")
async def touch_visa_requirements(requests: List[TouchRequest], _ = Security(verify_api_key)):
    try:
        async with db.pool.acquire() as conn:
            for req in requests:
                await conn.execute(
                    """
                    UPDATE visa_requirements 
                    SET last_verified_at = NOW() 
                    WHERE country = $1 AND visa_type = $2 AND issuing_body = $3
                    """,
                    req.country, req.visa_type, req.issuing_body
                )
        return {"status": "ok"}
    except Exception as e:
        logger.error("Visa requirements touch failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")
