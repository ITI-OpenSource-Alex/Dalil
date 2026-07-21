import pytest
import os
import httpx
from app.core.config import settings
from app.services.rag_service import generate_embedding, embedding_client

def is_ollama_running():
    try:
        resp = httpx.get("http://localhost:11434/api/tags")
        if resp.status_code == 200 and "nomic-embed-text" in resp.text:
            return True
    except Exception:
        pass
    return False

@pytest.mark.asyncio
async def test_embedding_dimension_is_768():
    if not is_ollama_running():
        pytest.skip("Ollama not running or nomic-embed-text not pulled")
    
    vec = await generate_embedding("test")
    assert len(vec) == 768, f"Expected 768-dimensional vector, got {len(vec)}"

def test_embeddings_client_targets_configured_base_url():
    # Assert the client points at settings.embedding_base_url, not api.openai.com
    assert getattr(settings, "embedding_base_url", None) is not None, "embedding_base_url setting is missing"
    assert str(embedding_client.base_url).rstrip("/") == settings.embedding_base_url.rstrip("/"), f"Embeddings model base URL is {embedding_client.base_url} but should be {settings.embedding_base_url}"

def test_no_openai_model_names_remain():
    bad_string = "text-embedding-" + "3-small"
    root_dirs = [".", "../ingestion"]
    for root_dir in root_dirs:
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        assert bad_string not in content, f"Found hardcoded OpenAI model name in {filepath}"
