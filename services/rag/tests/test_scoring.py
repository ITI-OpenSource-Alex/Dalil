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
    # For /match:
    mock_conn.fetch = AsyncMock(return_value=[{
        "id": "prog-1", "program_name": "Test Prog", "university": "Uni", 
        "country": "Germany", "deadline": None, "degree_level": "Master"
    }])

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
        "/score", json={"userId": "user-123", "programId": "prog-1"}
    )
    assert response.status_code == 425
    assert "Profile not yet replicated" in response.json()["detail"]


def test_scoring_success(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)

    response = client.post(
        "/score", json={"userId": "user-123", "programId": "prog-1"}
    )
    assert response.status_code == 200
    assert "score" in response.json()


def test_score_path_unchanged(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)
    response = client.post(
        "/score", json={"userId": "user-123", "programId": "prog-1"}
    )
    assert response.status_code == 200


def test_match_reachable_at_bare_path(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)

    res_old = client.post("/scoring/match", json={"userId": "user-123"})
    assert res_old.status_code == 404

    res_new = client.post("/match", json={"userId": "user-123"})
    assert res_new.status_code == 200


def test_match_response_key_is_programs(monkeypatch):
    _, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    
    # Return multiple programs to test sorting
    mock_conn.fetch = AsyncMock(return_value=[
        {"id": "prog-1", "program_name": "Prog 1", "university": "Uni 1", "country": "DE", "deadline": None, "degree_level": "Master"},
        {"id": "prog-2", "program_name": "Prog 2", "university": "Uni 2", "country": "DE", "deadline": None, "degree_level": "Bachelor"}
    ])
    # The calculate_score loop will call fetchrow twice per program (1: program, 2: user)
    # So for 2 programs we need 4 return values. We will return higher score for prog-2.
    mock_prog_1 = {
        "id": "prog-1", "min_ects": 120, "degree_level": "Bachelor",
        "required_citizenship": None, "min_ielts": 6.5, "min_gpa": 3.0, "min_work_experience": 1,
    }
    mock_prog_2 = {
        "id": "prog-2", "min_ects": 120, "degree_level": "Bachelor",
        "required_citizenship": None, "min_ielts": 8.5, "min_gpa": 4.0, "min_work_experience": 1,
    }
    mock_user = {
        "user_id": "user-123", "ects": 180, "gpa": 3.8, "gpa_scale": "4.0",
        "ielts_score": 7.5, "degree_level": "Bachelor", "work_exp": 2,
        "extracurriculars": 85, "target_countries": ["Germany"],
    }
    mock_conn.fetchrow.side_effect = [
        mock_prog_1, mock_user,  # calculation for prog-1
        mock_prog_2, mock_user   # calculation for prog-2
    ]
    
    # For prog-2, make the LLM boost higher so it wins (only applies to /score now)
    def mock_llm(cv_text=None, program_description=None, **kwargs):
        if program_description and "prog-2" in program_description:
            return {"boost_value": 20.0, "justification_tokens": ["Amazing"]}
        return {"boost_value": 5.0, "justification_tokens": ["Ok"]}
        
    mock_llm_async = AsyncMock(side_effect=mock_llm)
    monkeypatch.setattr("app.services.scoring.get_llm_boost", mock_llm_async)

    res = client.post("/match", json={"userId": "user-123"})
    assert res.status_code == 200
    data = res.json()
    
    assert "programs" in data
    assert "matches" not in data
    
    programs = data["programs"]
    assert len(programs) == 2
    # Ensure descending sort
    assert programs[0]["result"]["score"] >= programs[1]["result"]["score"]

def test_match_entries_carry_display_fields(monkeypatch):
    _, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    
    mock_conn.fetch = AsyncMock(return_value=[{
        "id": "prog-1",
        "program_name": "MSc Computer Science",
        "university": "TU Munich",
        "country": "Germany",
        "deadline": "2024-05-31"
    }])
    mock_conn.fetchrow.side_effect = [
        {
            "id": "prog-1", "min_ects": 120, "degree_level": "Master",
            "required_citizenship": None, "min_ielts": 6.5, "min_gpa": 3.0, "min_work_experience": 1,
        },
        {
            "user_id": "user-123", "ects": 180, "gpa": 3.8, "gpa_scale": "4.0",
            "ielts_score": 7.5, "degree_level": "Bachelor", "work_exp": 2,
            "extracurriculars": 85, "target_countries": ["Germany"],
        }
    ]
    res = client.post("/match", json={"userId": "user-123"})
    assert res.status_code == 200
    programs = res.json()["programs"]
    assert len(programs) == 1
    assert programs[0].get("programName") == "MSc Computer Science"
    assert programs[0].get("university") == "TU Munich"
    assert programs[0].get("country") == "Germany"
    assert programs[0].get("deadline") == "2024-05-31"

def test_match_null_name_falls_back(monkeypatch):
    _, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    
    mock_conn.fetch = AsyncMock(return_value=[{
        "id": "prog-1",
        "program_name": None,
        "university": "TU Munich",
        "country": "Germany",
        "deadline": None,
        "degree_level": "Master"
    }])
    mock_conn.fetchrow.side_effect = [
        {
            "id": "prog-1", "min_ects": 120, "degree_level": "Master",
            "required_citizenship": None, "min_ielts": 6.5, "min_gpa": 3.0, "min_work_experience": 1,
        },
        {
            "user_id": "user-123", "ects": 180, "gpa": 3.8, "gpa_scale": "4.0",
            "ielts_score": 7.5, "degree_level": "Bachelor", "work_exp": 2,
            "extracurriculars": 85, "target_countries": ["Germany"],
        }
    ]
    res = client.post("/match", json={"userId": "user-123"})
    assert res.status_code == 200
    programs = res.json()["programs"]
    assert len(programs) == 1
    assert programs[0].get("programName") == "TU Munich \u2014 Master"
    assert programs[0].get("university") == "TU Munich"

def test_match_missing_row_omitted(monkeypatch):
    _, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    # The program is in the db, but calculate_score raises 404 (e.g. deleted mid-loop)
    mock_conn.fetch = AsyncMock(return_value=[{
        "id": "prog-1",
        "program_name": "MSc Computer Science",
        "university": "TU Munich",
        "country": "Germany",
        "deadline": "2024-05-31"
    }])
    mock_conn.fetchrow.side_effect = [
        None,  # Program not found during calculate_score
        None
    ]
    res = client.post("/match", json={"userId": "user-123"})
    assert res.status_code == 200
    programs = res.json()["programs"]
    assert len(programs) == 0

def test_no_n_plus_one(monkeypatch):
    pool, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    
    # 5 programs
    programs_data = [{"id": f"prog-{i}", "program_name": f"Prog {i}", "university": "Uni", "country": "Germany", "deadline": None} for i in range(5)]
    mock_conn.fetch = AsyncMock(return_value=programs_data)
    
    fetchrow_returns = []
    for i in range(5):
        fetchrow_returns.extend([
            {"id": f"prog-{i}", "min_ects": 120, "degree_level": "Master", "required_citizenship": None, "min_ielts": 6.5, "min_gpa": 3.0, "min_work_experience": 1},
            {"user_id": "user-123", "ects": 180, "gpa": 3.8, "gpa_scale": "4.0", "ielts_score": 7.5, "degree_level": "Bachelor", "work_exp": 2, "extracurriculars": 85, "target_countries": ["Germany"]},
        ])
    mock_conn.fetchrow.side_effect = fetchrow_returns

    res = client.post("/match", json={"userId": "user-123"})
    assert res.status_code == 200
    
    # Assert fetch was called exactly once for the program list
    assert mock_conn.fetch.call_count == 1

def test_match_scores_concurrently_bounded(monkeypatch):
    import asyncio
    pool, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    
    # 12 programs
    programs_data = [{"id": f"prog-{i}", "program_name": f"Prog {i}", "university": "Uni", "country": "Germany", "deadline": None} for i in range(12)]
    mock_conn.fetch = AsyncMock(return_value=programs_data)
    
    # Mock calculate_score to track concurrency
    in_flight = 0
    max_in_flight = 0
    
    async def mock_calculate_score(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {"score": 50.0 + len(args[1])}
        
    monkeypatch.setattr("app.api.scoring.calculate_score", mock_calculate_score)

    res = client.post("/match", json={"userId": "user-123"})
    assert res.status_code == 200
    
    # Assert max concurrency was bounded (started at 5 per ticket)
    assert max_in_flight > 1
    assert max_in_flight <= 5
    
    programs = res.json()["programs"]
    assert len(programs) == 12
    # Check sorted
    for i in range(11):
        assert programs[i]["result"]["score"] >= programs[i+1]["result"]["score"]


@pytest.mark.asyncio
async def test_local_user_profile_coerces_uuid_user_id(monkeypatch):
    """Regression: local_user_profiles.user_id is a UUID column, so asyncpg returns a
    uuid.UUID object. UserProfile.userId is typed str, so without coercion every real
    row raised a ValidationError and /match returned an empty list for every user.
    The other tests in this file mock user_id as the string "user-123", which is why
    they stayed green while the live endpoint was broken."""
    import uuid as uuid_mod
    from app.services.scoring import get_local_user_profile

    real_uuid = uuid_mod.UUID("00000000-0000-0000-0000-000000000002")

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        "user_id": real_uuid,          # a UUID object, exactly as asyncpg returns it
        "ects": 130,
        "gpa": 3.5,
        "gpa_scale": "4.0",
        "ielts_score": 7.0,
        "degree_level": "Master",
        "work_exp": 3,
        "extracurriculars": 80,
        "target_countries": [],
    })
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)
    monkeypatch.setattr("app.core.database.db.pool", mock_pool)

    profile = await get_local_user_profile(real_uuid)

    assert isinstance(profile["userId"], str)
    assert profile["userId"] == "00000000-0000-0000-0000-000000000002"

    # And it must satisfy the Pydantic model that consumes it — the actual failure point.
    from app.schemas.scoring import UserProfile
    assert UserProfile(**profile).userId == "00000000-0000-0000-0000-000000000002"

def test_match_issues_zero_llm_calls(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)
    mock_llm = AsyncMock(return_value={"boost_value": 10.0, "justification_tokens": ["Great CV"]})
    monkeypatch.setattr("app.services.scoring.get_llm_boost", mock_llm)
    
    response = client.post("/match", json={"userId": "user-123"})
    assert response.status_code == 200
    assert mock_llm.call_count == 0

def test_score_still_applies_boost(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)
    mock_llm = AsyncMock(return_value={"boost_value": 10.0, "justification_tokens": ["Great CV"]})
    monkeypatch.setattr("app.services.scoring.get_llm_boost", mock_llm)
    
    response = client.post("/score", json={"userId": "user-123", "programId": "prog-1"})
    assert response.status_code == 200
    assert mock_llm.call_count == 1

def test_match_ranking_order_unchanged(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)
    response = client.post("/match", json={"userId": "user-123"})
    assert response.status_code == 200
    programs = response.json()["programs"]
    assert len(programs) > 0
    scores = [p["result"]["score"] for p in programs]
    assert scores == sorted(scores, reverse=True)

