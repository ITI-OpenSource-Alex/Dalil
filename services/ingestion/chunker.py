import uuid
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Deterministic namespace for UUID v5 generation
INGESTION_NAMESPACE = uuid.UUID('e2a4be5a-d1e9-4e78-bc46-56ffccb4e138')

def get_chunker() -> RecursiveCharacterTextSplitter:
    """
    Returns a RecursiveCharacterTextSplitter configured to measure length
    in tokens using the cl100k_base tiktoken encoding.
    """

    try:
        # Direct lookup using the cl100k_base encoding (used by text-embedding-3-small)
        # to avoid internal model-to-encoding lookup failures on older/newer package versions.
        return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=500,
            chunk_overlap=50,
        )
    
    except Exception as e:
        # Fallback to model name if encoding_name parameter is not supported by a specific version
        return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            model_name = 'text-embedding-3-small',
            chunk_size=500,
            chunk_overlap=50
        )
    
def generate_chunk_id(source_url: str, content: str) -> str:
    """Generates a deterministic UUID v5 from a source URL and content prefix."""
    url_str = source_url or ""
    unique_key = f"{url_str}{content[:100]}"
    return str(uuid.uuid5(INGESTION_NAMESPACE, unique_key))

def chunk_documents(documents: list[Document]) -> list[Document]:
    """
    Splits input documents into chunks of at most 500 tokens with 50 tokens overlap.
    Enriches each chunk's metadata with a deterministic ID.
    """

    splitter = get_chunker()
    chunks = splitter.split_documents(documents)
    
    for chunk in chunks:
        source_url = chunk.metadata.get("source_url")
        chunk.metadata["id"] = generate_chunk_id(source_url, chunk.page_content)
    
    return chunks
