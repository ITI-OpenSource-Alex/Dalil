from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID


class DocumentCheckRequest(BaseModel):
    ids: List[UUID] = Field(
        ..., description="List of document IDs to check for existence"
    )


class DocumentCheckResponse(BaseModel):
    existing_ids: List[UUID] = Field(..., description="List of existing document IDs")


class DocumentUpsertItem(BaseModel):
    id: UUID = Field(..., description="The database UUID of the document chunk")
    content: str = Field(..., description="The text content of the chunk")
    embedding: List[float] = Field(..., description="The embedding vector of the chunk")
    source_url: Optional[str] = Field(None, description="The source URL of the chunk")
    category: Optional[str] = Field(None, description="The category classification")


class DocumentUpsertRequest(BaseModel):
    documents: List[DocumentUpsertItem] = Field(
        ..., description="List of documents to upsert"
    )
