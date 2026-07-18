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
        SELECT id, country, visa_type, issuing_body, source_url, fetch_method
        FROM visa_sources
        WHERE active IS TRUE
        ORDER BY country, issuing_body
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
