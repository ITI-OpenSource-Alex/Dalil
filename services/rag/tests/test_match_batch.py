"""Option B prerequisite: /match must pre-filter, batch-score, rank and limit.

The previous implementation scored EVERY row in program_requirements, issuing two
queries per program (profile + program) plus a Redis get/set each. At the ~20,000
in-scope European Engineering/CS programs that is ~40,000 round trips per request.
These tests pin the properties that make the full catalog survivable.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.scoring import ProgramRequirements, UserProfile
from app.services.scoring import (
    MATCH_RESULT_LIMIT,
    discipline_for_field_of_study,
    match_programs,
    score_profile_against_program,
)


# --------------------------------------------------------------- pure scoring core


def _profile(**over):
    base = dict(
        userId="u1",
        degreeLevel="Master",
        gpa=3.5,
        gpaScale="4.0",
        ieltsScore=7.0,
        workExperienceYears=2,
        extracurricularsScore=5,
    )
    base.update(over)
    return UserProfile(**base)


def test_shared_scorer_returns_zero_and_reason_when_gated():
    # Diploma -> PhD, i.e. genuinely under-qualified. This used to be
    # Bachelor -> Master, which the degree gate no longer blocks: holding the
    # rung below a programme is its prerequisite, not a disqualification.
    result = score_profile_against_program(
        _profile(degreeLevel="Diploma"),
        ProgramRequirements(id="p", degree_level="PhD"),
    )
    assert result["score"] == 0.0
    assert result["blocked_by"] == "degree_level"


def test_shared_scorer_attaches_finance_items_when_supplied():
    finance = [
        {"type": "informational", "country": "Germany", "source_url": "https://x"}
    ]
    result = score_profile_against_program(
        _profile(), ProgramRequirements(id="p", country="Germany"), finance
    )
    assert result["gap_report"]["financial"] == finance


def test_shared_scorer_omits_financial_key_without_items():
    result = score_profile_against_program(_profile(), ProgramRequirements(id="p"))
    assert "financial" not in result["gap_report"]


# ------------------------------------------------------- field of study -> discipline


@pytest.mark.parametrize(
    "field, expected",
    [
        ("Computer Science", "computer_science"),
        (
            "software engineering",
            "computer_science",
        ),  # 'software' wins before 'engineer'
        ("Data Science", "computer_science"),
        ("Cybersecurity", "computer_science"),
        ("Mechanical Engineering", "engineering"),
        ("Robotics", "engineering"),
        ("Art History", None),  # unmapped -> no discipline filter
        ("", None),
        (None, None),
    ],
)
def test_discipline_mapping(field, expected):
    assert discipline_for_field_of_study(field) == expected


# ----------------------------------------------------------------- the batch path


def _row(pid, country="Germany", name="Prog", discipline="computer_science", ielts=6.0):
    return {
        "id": pid,
        "program_name": name,
        "university": "Uni",
        "country": country,
        "deadline": None,
        "discipline": discipline,
        "degree_level": "Master",
        "min_ects": 120,
        "min_gpa": None,
        "min_ielts": ielts,
        "required_citizenship": None,
        "min_work_experience": None,
        "source_url": "https://www.mastersportal.com/studies/1/example.html",
        "last_scraped_at": None,
    }


def _wire(monkeypatch, rows, profile_over=None, cached=None):
    """Patch the DB pool, Redis and the finance lookup for match_programs()."""
    import app.services.scoring as sc

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(sc.db, "pool", pool)

    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    monkeypatch.setattr(sc.redis_client, "redis", redis)

    profile = dict(
        userId="u1",
        degreeLevel="Master",
        gpa=3.5,
        gpaScale="4.0",
        ieltsScore=7.0,
        workExperienceYears=2,
        extracurricularsScore=5,
        targetCountries=[],
        fieldOfStudy=None,
    )
    profile.update(profile_over or {})
    monkeypatch.setattr(sc, "get_local_user_profile", AsyncMock(return_value=profile))

    finance = AsyncMock(return_value=[])
    monkeypatch.setattr(sc, "get_student_visa_finance", finance)
    return conn, redis, finance


@pytest.mark.asyncio
async def test_match_caps_results_at_the_limit(monkeypatch):
    rows = [
        _row(f"p{i}", ielts=5.0 + (i % 4) * 0.5) for i in range(MATCH_RESULT_LIMIT + 10)
    ]
    _wire(monkeypatch, rows)
    results = await match_programs("u1")
    assert len(results) == MATCH_RESULT_LIMIT


@pytest.mark.asyncio
async def test_match_results_are_sorted_descending(monkeypatch):
    rows = [_row(f"p{i}", ielts=ielts) for i, ielts in enumerate((7.0, 5.0, 6.5, 5.5))]
    _wire(monkeypatch, rows)
    scores = [r["result"]["score"] for r in await match_programs("u1")]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_match_scores_in_memory_with_one_candidate_query(monkeypatch):
    """The anti-regression guard: no per-program query fan-out."""
    conn, _, _ = _wire(monkeypatch, [_row(f"p{i}") for i in range(25)])
    await match_programs("u1")
    # One catalogue query plus one visa query per distinct country; still no
    # per-program fan-out.
    assert conn.fetch.await_count <= 2


@pytest.mark.asyncio
async def test_match_passes_country_and_discipline_filters_to_sql(monkeypatch):
    conn, _, _ = _wire(
        monkeypatch,
        [_row("p1")],
        profile_over={
            "targetCountries": ["Germany"],
            "fieldOfStudy": "Computer Science",
        },
    )
    await match_programs("u1")
    args = conn.fetch.await_args_list[0].args
    assert args[1] == ["Germany"]
    assert args[2] == "computer_science"
    assert args[4] is False  # demo provenance excluded by default


@pytest.mark.asyncio
async def test_absent_preferences_widen_rather_than_empty_the_search(monkeypatch):
    """A profile with no target countries and no field of study must still get
    results — the seeded demo profile has both NULL."""
    conn, _, _ = _wire(
        monkeypatch,
        [_row("p1"), _row("p2")],
        profile_over={"targetCountries": [], "fieldOfStudy": None},
    )
    results = await match_programs("u1")
    args = conn.fetch.await_args_list[0].args
    assert args[1] is None and args[2] is None  # both filters disabled
    assert len(results) == 2


@pytest.mark.asyncio
async def test_intended_software_field_filters_unrelated_titles(monkeypatch):
    rows = [
        _row("software", name="Software Engineering"),
        _row("computer", name="Computer Science"),
        _row("planning", name="Spatial Planning"),
        _row("agriculture", name="Agricultural Science and Technology"),
        _row("data", name="Data Science and AI for Business"),
    ]
    _wire(
        monkeypatch,
        rows,
        profile_over={
            "fieldOfStudy": "Software Engineering",
            "targetFieldOfStudy": "Software Engineering",
        },
    )

    results = await match_programs("u1")

    assert [result["programName"] for result in results] == [
        "Software Engineering",
        "Computer Science",
    ]


@pytest.mark.asyncio
async def test_intended_electrical_field_keeps_only_exact_and_defensible_adjacent_titles(
    monkeypatch,
):
    rows = [
        _row("electronic", name="Electronic Engineering"),
        _row(
            "automation",
            name="Automation Engineering and Control of Complex Systems",
        ),
        _row("aerospace", name="Aerospace Engineering"),
        _row("civil", name="Civil Systems Engineering"),
        _row("energy", name="Energy Engineering"),
    ]
    _wire(
        monkeypatch,
        rows,
        profile_over={
            "fieldOfStudy": "Electrical Engineering",
            "targetFieldOfStudy": "Electrical Engineering",
        },
    )

    results = await match_programs("u1")

    assert [result["programName"] for result in results] == [
        "Electronic Engineering",
        "Automation Engineering and Control of Complex Systems",
    ]


@pytest.mark.asyncio
async def test_finance_lookup_is_once_per_country_not_per_program(monkeypatch):
    rows = [_row(f"de{i}", country="Germany") for i in range(6)] + [
        _row(f"uk{i}", country="United Kingdom") for i in range(4)
    ]
    _, _, finance = _wire(monkeypatch, rows)
    await match_programs("u1")
    assert finance.await_count == 2


@pytest.mark.asyncio
async def test_match_serves_from_cache_without_touching_the_db(monkeypatch):
    """E2E RAG-05: repeating the call within the hour must not re-score."""
    cached = json.dumps([{"programId": "p1", "result": {"score": 91.0}}])
    conn, _, _ = _wire(monkeypatch, [], cached=cached)
    results = await match_programs("u1")
    assert results[0]["programId"] == "p1"
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_raises_425_when_profile_not_replicated(monkeypatch):
    import app.services.scoring as sc
    from fastapi import HTTPException

    _wire(monkeypatch, [])
    monkeypatch.setattr(sc, "get_local_user_profile", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await match_programs("u1")
    assert exc.value.status_code == 425
