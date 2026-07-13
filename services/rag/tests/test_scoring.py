import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_mock_db_pool(monkeypatch, return_user=True):
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    if return_user:
        mock_user_row = {
            "user_id": "user-123",
            "ects": 180,
            "gpa": 3.8,
            "gpa_scale": "4.0",
            "ielts_score": 7.5,
            "degree_level": "Bachelor",
            "work_exp": 2,
            "extracurriculars": 85,
            "target_countries": ["Germany"],
        }
    else:
        mock_user_row = None

    mock_program_row = {
        "id": "prog-1",
        "min_ects": 120,
        "degree_level": "Bachelor",
        "required_citizenship": None,
        "min_ielts": 6.5,
        "min_gpa": 3.0,
        "min_work_experience": 1,
    }

    # Sequence of fetchrow calls: 1) Program 2) User
    mock_conn.fetchrow.side_effect = [mock_program_row, mock_user_row]

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    monkeypatch.setattr("app.core.database.db.pool", mock_pool)
    return mock_pool, mock_conn


@pytest.fixture(autouse=True)
def mock_external(monkeypatch):
    mock_cv = AsyncMock(return_value="Student CV content")
    monkeypatch.setattr("app.services.scoring.get_user_cv", mock_cv)

    mock_llm = AsyncMock(
        return_value={"boost_value": 10.0, "justification_tokens": ["Great CV"]}
    )
    monkeypatch.setattr("app.services.scoring.get_llm_boost", mock_llm)

    # Disable Redis for tests
    monkeypatch.setattr("app.core.redis.redis_client.redis", None)


def test_scoring_returns_425_if_no_local_profile(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=False)

    response = client.post(
        "/scoring/score", json={"userId": "user-123", "programId": "prog-1"}
    )
    assert response.status_code == 425
    assert "Profile not yet replicated" in response.json()["detail"]


def test_scoring_success(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)

    response = client.post(
        "/scoring/score", json={"userId": "user-123", "programId": "prog-1"}
    )
    assert response.status_code == 200
    assert "score" in response.json()
