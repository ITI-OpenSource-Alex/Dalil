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
    title: Optional[str] = Field(None, description="The document title parsed from stored metadata")
    url: Optional[str] = Field(None, alias="source_url", description="The source URL of the chunk")
    content: str = Field(..., description="The text content of the chunk")
    relevance_score: float = Field(..., alias="similarity", description="Cosine relevance score (0.0 to 1.0)")
    class Config:
        populate_by_name = True

class QueryResponse(BaseModel):
    answer: Optional[str] = Field(None, description="The generated answer, or None if confidence is low")
    reason: Optional[str] = Field(None, description="Refusal reason if answer is None (e.g. insufficient_data)")
    suggestion: Optional[str] = Field(None, description="User suggestion when query is refused")
    sources: List[DocumentSource] = Field(
        default=[], description="The context sources retrieved"
    )
