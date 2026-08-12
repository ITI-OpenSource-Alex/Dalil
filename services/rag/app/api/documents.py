from fastapi import APIRouter, Security, HTTPException, status
from app.core.database import db
from app.core.security import verify_api_key
from app.schemas.documents import (
    DocumentCheckRequest,
    DocumentCheckResponse,
    DocumentUpsertRequest,
)


router = APIRouter()


@router.get("/internal/documents/stats")
async def document_stats(_=Security(verify_api_key)):
    """Return corpus readiness without exposing document bodies.

    Ingestion and demo tooling use this owner API instead of querying rag_db.
    """
    try:
        async with db.pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM documents")
            rows = await conn.fetch(
                "SELECT category, COUNT(*) AS count FROM documents GROUP BY category"
            )
            last_updated = await conn.fetchval("SELECT MAX(last_updated) FROM documents")
        return {
            "total": total,
            "by_category": {row["category"]: row["count"] for row in rows},
            "last_updated_at": last_updated,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}",
        )


@router.post("/internal/documents/check-existing", response_model=DocumentCheckResponse)
async def check_existing_documents(
    request: DocumentCheckRequest, _=Security(verify_api_key)
):
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE id = ANY($1)", request.ids
            )
            existing_ids = [row["id"] for row in rows]
            return DocumentCheckResponse(existing_ids=existing_ids)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}",
        )


@router.post("/internal/documents")
async def upsert_documents(request: DocumentUpsertRequest, _=Security(verify_api_key)):
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                ids = [doc.id for doc in request.documents]
                existing_rows = await conn.fetch(
                    "SELECT id FROM documents WHERE id = ANY($1)", ids
                )
                existing_ids = {row["id"] for row in existing_rows}
                for doc in request.documents:
                    await conn.execute(
                        """
                        INSERT INTO documents (id, content, embedding, source_url, category, last_updated)
                        VALUES ($1, $2, $3::vector, $4, $5, NOW())
                        ON CONFLICT (id) DO UPDATE
                        SET content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            source_url = EXCLUDED.source_url,
                            category = EXCLUDED.category,
                            last_updated = NOW()
                        """,
                        doc.id,
                        doc.content,
                        doc.embedding,
                        doc.source_url,
                        doc.category,
                    )
        updated = sum(1 for doc in request.documents if doc.id in existing_ids)
        return {
            "status": "success",
            "count": len(request.documents),
            "added": len(request.documents) - updated,
            "updated": updated,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database upsert failed: {str(e)}",
        )


@router.delete("/internal/documents")
async def delete_documents_by_source_url(
    source_url: str, _=Security(verify_api_key)
):
    """Delete the old tier's chunks before richer chunks for the same source land."""
    try:
        async with db.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE source_url = $1", source_url
            )
        return {"status": "success", "deleted": int(result.rsplit(" ", 1)[-1])}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database delete failed: {str(e)}",
        )
