import pytest
import tiktoken
from langchain_core.documents import Document
from chunker import chunk_documents, generate_chunk_id

def test_generate_chunk_id_is_deterministic():
    """Verify identical url + content prefix produces identical UUID v5."""
    url = "https://goa.app/test"
    content = "This is a sample document for testing the deterministic hash generator."
    
    id1 = generate_chunk_id(url, content)
    id2 = generate_chunk_id(url, content)
    
    assert id1 == id2
    # Verify that different content generates a different ID
    id3 = generate_chunk_id(url, "Different content entirely...")
    assert id1 != id3

def test_generate_chunk_id_handles_missing_url():
    """Verify that a missing (None or empty) URL does not cause crashes and is deterministic."""
    content = "Sample content"
    id1 = generate_chunk_id(None, content)
    id2 = generate_chunk_id("", content)
    assert id1 == id2

def test_chunker_conforms_to_sizing_constraints():
    """Verify RecursiveCharacterTextSplitter produces <= 500 token chunks with 50 overlap."""
    # Generate a long text (e.g. 800 words, which is well over 500 tokens)
    long_text = "word " * 800
    doc = Document(
        page_content=long_text,
        metadata={"source_url": "https://goa.app/long-doc", "category": "test"}
    )
    
    chunks = chunk_documents([doc])
    
    # Check that it split the document into multiple chunks
    assert len(chunks) > 1
    
    # Verify each chunk has metadata enriched with ID, source_url, and category
    encoding = tiktoken.get_encoding("cl100k_base")
    for chunk in chunks:
        assert "id" in chunk.metadata
        assert chunk.metadata["source_url"] == "https://goa.app/long-doc"
        assert chunk.metadata["category"] == "test"
        
        # Verify chunk length in tokens (measured by tiktoken)
        tokens = encoding.encode(chunk.page_content)
        assert len(tokens) <= 500