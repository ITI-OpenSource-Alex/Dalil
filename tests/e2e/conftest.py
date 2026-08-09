import os

import pytest


DEFAULT_EXAM_BASE_URL = os.getenv("GOA_EXAM_BASE_URL", "http://localhost:8085")
DEFAULT_INTERNAL_API_KEY = os.getenv(
    "GOA_INTERNAL_API_KEY", "supersecret_internal_key_123"
)


@pytest.fixture(scope="session")
def exam_base_url() -> str:
    return DEFAULT_EXAM_BASE_URL


@pytest.fixture(scope="session")
def internal_headers() -> dict[str, str]:
    return {"X-Internal-API-Key": DEFAULT_INTERNAL_API_KEY}
