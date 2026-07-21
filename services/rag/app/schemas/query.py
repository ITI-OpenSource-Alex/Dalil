from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    question: str = Field(..., description="The query question from the user")
    userId: str = Field(..., description="The ID of the user submitting the query")
    topK: Optional[int] = Field(
        5, description="Number of source document chunks to retrieve"
    )


class DocumentSource(BaseModel):
    id: str = Field(..., description="The database UUID of the document chunk")
    content: str = Field(..., description="The text content of the chunk")
    source_url: Optional[str] = Field(None, description="The source URL of the chunk")
    similarity: float = Field(..., description="Cosine similarity score (0 to 1)")


class QueryResponse(BaseModel):
    answer: str = Field(..., description="The generated answer from Claude")
    sources: List[DocumentSource] = Field(
        default=[], description="The retrieved context sources used"
    )
