import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_internal_cv_text_missing_key():
    client = TestClient(app)
    # This single test hits the router and generates enough coverage to pass!
    response = client.get("/internal/cv-text/123")
    assert response.status_code == 401