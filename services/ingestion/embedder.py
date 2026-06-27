import logging
from openai import OpenAI
from config import settings

logger = logging.getLogger('ingestion_worker.embedder')

def get_openai_client() -> OpenAI:
    """Initializes and returns the OpenAI client using the configured API key."""
    return OpenAI(api_key=settings.openai_api_key)

def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generates embeddings for a list of texts using the text-embedding-3-small model.
    Batches texts in groups of up to 100 to optimize rate limits and latency.
    """
     
    if not texts:
        return []
    client = get_openai_client()
    embeddings = []
    batch_size = 100

    for i in range(0, len(texts), batch_size):
        batch = texts[i: i+batch_size]
        logger.info("Generating embeddings for batch of %d items (indices %d-%d)", len(batch), i, i + len(batch) - 1)
        try:
            response = client.embeddings.create(
                model = "text-embedding-3-small",
                input = batch
            )
            batch_embeddings = [data.embedding for data in response.data]
            embeddings.extend(batch_embeddings)
        except Exception as e:
            logger.error("OpenAI embeddings generation failed: %s", str(e))
            raise e
    
    return embeddings