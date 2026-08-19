import pytest

@pytest.fixture(autouse=True)
def set_test_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "768")
