from fastapi import APIRouter, Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from typing import List
from uuid import UUID


from app.core.config import settings
from app.core.database import db
from app.schemas.documents import (
    DocumentCheckRequest,
    DocumentCheckResponse,
    DocumentUpsertRequest
)


router = APIRouter()
API_KEY_NAME = 'X-Internal-API-Key'
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(header_key: str = Security(api_key_header)):
    if not header_key or header_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Api-Key header"
        )
    return header_key




@router.post('/internal/documents/check-existing', response_model=DocumentCheckResponse)
async def check_existing_documents(request: DocumentCheckRequest, _ = Security(verify_api_key)):
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE id = ANY($1)",
                request.ids
            )
            existing_ids = [row['id'] for row in rows]
            return DocumentCheckResponse(existing_ids=existing_ids)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )
    
@router.post('/internal/documents')
async def upsert_documents(request: DocumentUpsertRequest, _ = Security(verify_api_key)):
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
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
                        doc.category
                    )
        return {"status": "success", "count": len(request.documents)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database upsert failed: {str(e)}"
        )
                
                

    

