import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_visa_finance_lookup(monkeypatch):
    """GOA-108's financial gap items are exercised in test_visa_task6.py.

    These scoring tests mock the DB connection generically, so once program.country
    became populated the live visa lookup started running against a non-awaitable
    MagicMock. Stub it to empty here so each test keeps asserting one thing."""
    import app.services.visa_finance as vf
    monkeypatch.setattr(vf, "get_student_visa_finance", AsyncMock(return_value=[]))


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
            # /match discipline pre-filtering reads this (migration 022).
            "field_of_study": None,
        }
    else:
        mock_user_row = None

    mock_program_row = {
        "id": "prog-1",
        "country": "Germany", "min_ects": 120,
        "degree_level": "Bachelor",
        "required_citizenship": None,
        "min_ielts": 6.5,
        "min_gpa": 3.0,
        "min_work_experience": 1,
    }

    # Sequence of fetchrow calls: 1) Program 2) User
    mock_conn.fetchrow.side_effect = [mock_program_row, mock_user_row]
    # For /match:
    # /match now fetches its whole candidate set (with requirements) in ONE query
    # instead of a per-program fan-out, so the mocked row carries every column.
    mock_conn.fetch = AsyncMock(return_value=[{
        "id": "prog-1", "program_name": "Test Prog", "university": "Uni",
        "country": "Germany", "deadline": None, "degree_level": "Master",
        "discipline": "computer_science", "min_ects": 120, "min_gpa": None,
        "min_ielts": 6.0, "required_citizenship": None, "min_work_experience": None,
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


USER_ROW = {
    "user_id": "user-123", "ects": 180, "gpa": 3.8, "gpa_scale": "4.0",
    "ielts_score": 7.5, "degree_level": "Master", "work_exp": 2,
    "extracurriculars": 85, "target_countries": ["Germany"], "field_of_study": None,
}


def _candidate(pid, name="Prog", ielts=6.0, university="Uni", country="Germany",
               deadline=None, degree_level="Master"):
    """A row as /match's single candidate query returns it (requirements included)."""
    return {
        "id": pid, "program_name": name, "university": university, "country": country,
        "deadline": deadline, "discipline": "computer_science", "degree_level": degree_level,
        "min_ects": 120, "min_gpa": None, "min_ielts": ielts,
        "required_citizenship": None, "min_work_experience": None,
    }


def _wire_match(monkeypatch, candidates):
    """/match fetches the profile once (fetchrow), then all candidates (fetch).

    Note the ordering is the reverse of the old fan-out design, which fetched the
    program list first and then re-queried profile+program for every program.
    """
    _, mock_conn = make_mock_db_pool(monkeypatch, return_user=True)
    mock_conn.fetchrow.side_effect = [USER_ROW]
    mock_conn.fetch = AsyncMock(return_value=candidates)
    return mock_conn


def test_match_reachable_at_bare_path(monkeypatch):
    _wire_match(monkeypatch, [_candidate("prog-1")])
    assert client.post("/scoring/match", json={"userId": "user-123"}).status_code == 404

    _wire_match(monkeypatch, [_candidate("prog-1")])
    assert client.post("/match", json={"userId": "user-123"}).status_code == 200


def test_match_response_key_is_programs_and_sorted(monkeypatch):
    _wire_match(monkeypatch, [
        _candidate("prog-1", ielts=7.5),   # only just met -> lower fit
        _candidate("prog-2", ielts=5.5),   # comfortably cleared -> higher fit
    ])
    data = client.post("/match", json={"userId": "user-123"}).json()
    assert "programs" in data and "matches" not in data
    scores = [p["result"]["score"] for p in data["programs"]]
    assert scores == sorted(scores, reverse=True)


def test_match_entries_carry_display_fields(monkeypatch):
    _wire_match(monkeypatch, [_candidate(
        "prog-1", name="MSc Computer Science", university="TU Munich",
        deadline="2024-05-31",
    )])
    programs = client.post("/match", json={"userId": "user-123"}).json()["programs"]
    assert len(programs) == 1
    assert programs[0]["programName"] == "MSc Computer Science"
    assert programs[0]["university"] == "TU Munich"
    assert programs[0]["country"] == "Germany"
    assert programs[0]["deadline"] == "2024-05-31"


def test_match_null_name_falls_back(monkeypatch):
    _wire_match(monkeypatch, [_candidate("prog-1", name=None, university="TU Munich")])
    programs = client.post("/match", json={"userId": "user-123"}).json()["programs"]
    assert programs[0]["programName"] == "TU Munich — Master"


def test_match_returns_at_most_the_result_limit(monkeypatch):
    from app.services.scoring import MATCH_RESULT_LIMIT
    _wire_match(monkeypatch, [_candidate(f"prog-{i}", ielts=5.0 + (i % 5) * 0.5)
                              for i in range(25)])
    programs = client.post("/match", json={"userId": "user-123"}).json()["programs"]
    assert len(programs) == MATCH_RESULT_LIMIT


def test_match_uses_one_candidate_query_no_fan_out(monkeypatch):
    """Replaces the old test_no_n_plus_one: scoring is in memory, so there is no
    per-program query at all. Concurrency-bounding (the old Semaphore(5) test) and the
    per-program 404-skip path no longer exist by design — a single candidate query
    cannot return a row that isn't there."""
    mock_conn = _wire_match(monkeypatch, [_candidate(f"prog-{i}") for i in range(10)])
    assert client.post("/match", json={"userId": "user-123"}).status_code == 200
    # Exactly one profile fetchrow, and no per-program fan-out: the candidate set and
    # the per-country finance lookups are the only fetch() calls, and both are bounded
    # by distinct countries rather than by program count.
    assert mock_conn.fetchrow.call_count == 1
    assert mock_conn.fetch.call_count <= 2


def test_match_issues_zero_llm_calls(monkeypatch):
    """GOA-125: ranking must not invoke the Stage-3 boost."""
    _wire_match(monkeypatch, [_candidate(f"prog-{i}") for i in range(3)])
    mock_llm = AsyncMock(return_value={"boost_value": 10.0, "justification_tokens": []})
    monkeypatch.setattr("app.services.scoring.get_llm_boost", mock_llm)
    assert client.post("/match", json={"userId": "user-123"}).status_code == 200
    mock_llm.assert_not_awaited()


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
        "field_of_study": None,
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

def test_score_still_applies_boost(monkeypatch):
    make_mock_db_pool(monkeypatch, return_user=True)
    mock_llm = AsyncMock(return_value={"boost_value": 10.0, "justification_tokens": ["Great CV"]})
    monkeypatch.setattr("app.services.scoring.get_llm_boost", mock_llm)
    
    response = client.post("/score", json={"userId": "user-123", "programId": "prog-1"})
    assert response.status_code == 200
    assert mock_llm.call_count == 1

def test_match_ranking_order_unchanged(monkeypatch):
    _wire_match(monkeypatch, [_candidate("prog-1", ielts=5.5), _candidate("prog-2", ielts=7.5)])
    response = client.post("/match", json={"userId": "user-123"})
    assert response.status_code == 200
    programs = response.json()["programs"]
    assert len(programs) > 0
    scores = [p["result"]["score"] for p in programs]
    assert scores == sorted(scores, reverse=True)

