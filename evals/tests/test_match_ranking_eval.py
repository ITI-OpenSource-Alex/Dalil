import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from evals.match_ranking_eval import (
    compute_ndcg,
    calculate_mock_soft_score,
    run_program_fit_weight_sweep,
)

def test_ranking_eval_is_deterministic():
    profile = {"gpa": 3.8, "ielts": 7.5, "degree": "Master", "target_countries": ["Germany"]}
    program = {"id": "p1", "degree": "Master", "country": "Germany"}
    
    s1 = calculate_mock_soft_score(profile, program, fit_weight=0.65)
    s2 = calculate_mock_soft_score(profile, program, fit_weight=0.65)
    assert s1 == s2

def test_weight_sweep_covers_configured_values():
    profiles = [{"gpa": 3.5, "ielts": 7.0, "degree": "Master", "target_countries": ["Germany"]}]
    programs = [
        {"id": "p1", "degree": "Master", "country": "Germany"},
        {"id": "p2", "degree": "Bachelor", "country": "USA"}
    ]
    expected = ["p1", "p2"]
    weights = [0.35, 0.50, 0.65, 0.80]
    
    sweep_results = run_program_fit_weight_sweep(profiles, programs, expected, weights)
    assert set(sweep_results.keys()) == set(weights)
    assert all(0.0 <= val <= 1.0 for val in sweep_results.values())

def test_ranking_quality_metric_matches_hand_computed_example():
    actual = ["p1", "p2", "p3"]
    expected = ["p1", "p2", "p3"]
    assert compute_ndcg(actual, expected) == 1.0

    reversed_actual = ["p3", "p2", "p1"]
    assert compute_ndcg(reversed_actual, expected) < 1.0


# --- The sweep that actually justifies PROGRAM_FIT_WEIGHT (DoD: "chosen from the
# --- sweep, with the reasoning recorded"). The sweep above scores a mock function
# --- that shares nothing with production, so it could never justify anything.

import pytest

RAG_APP = Path(__file__).resolve().parents[2] / "services" / "rag"


def _load_real_scorer():
    if str(RAG_APP) not in sys.path:
        sys.path.insert(0, str(RAG_APP))
    try:
        from app.schemas.scoring import UserProfile, ProgramRequirements
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"rag service not importable: {exc}")
    return UserProfile, ProgramRequirements


def _catalog():
    UserProfile, ProgramRequirements = _load_real_scorer()
    profile = UserProfile(
        userId="u1", degreeLevel="Master", gpa=3.4, gpaScale="4.0", ieltsScore=7.0,
        ects=180, workExperienceYears=2, extracurricularsScore=40,
        targetCountries=["Germany"], fieldOfStudy="Computer Science",
    )
    programs, i = [], 0
    for ielts in (None, 6.0, 6.5, 7.0):
        for gpa in (None, 2.5, 3.0, 3.3):
            for ects in (None, 180):
                i += 1
                programs.append(ProgramRequirements(
                    id=f"p{i}", country="Germany", degree_level="Master",
                    min_ielts=ielts, min_gpa=gpa, min_ects=ects,
                    min_work_experience=None,
                ))
    return profile, programs


def test_zero_fit_weight_collapses_the_ranking():
    """The regression this constant exists to prevent: at weight 0 every program
    that passes the gate scores identically — the 83.46 tie, reproduced on demand."""
    from evals.match_ranking_eval import run_real_program_fit_sweep
    profile, programs = _catalog()
    result = run_real_program_fit_sweep(profile, programs, weights=(0.0,))[0.0]
    assert result["distinct_scores"] == 1
    assert result["spread"] == 0.0


def test_ranking_quality_is_flat_across_every_non_zero_weight():
    """What the sweep actually establishes — and what it does not.

    Ordering quality and score distinctness are IDENTICAL for every non-zero weight;
    only the spread grows, linearly. So the sweep settles exactly one question — the
    weight must not be zero — and cannot select 0.35 over 0.5 or 0.15. The magnitude
    is a product judgement about how far program fit may displace a candidate's
    absolute strength, and it should be recorded as such rather than dressed up as an
    empirical optimum. The first version of this test asserted 0.35 was the cheapest
    point on a plateau; it passed on one catalog and failed on another, which is how
    the flatness came to light.
    """
    from evals.match_ranking_eval import run_real_program_fit_sweep
    from app.services.soft_score import PROGRAM_FIT_WEIGHT

    profile, programs = _catalog()
    weights = (0.15, 0.25, 0.35, 0.5, 0.65, 0.8)
    results = run_real_program_fit_sweep(profile, programs, weights=weights)

    assert PROGRAM_FIT_WEIGHT in weights, "production weight is not covered by the sweep"
    assert len({r["dominance_accuracy"] for r in results.values()}) == 1
    assert len({r["distinct_scores"] for r in results.values()}) == 1

    # Spread is the only thing the weight controls, and it is monotone in it.
    spreads = [results[w]["spread"] for w in weights]
    assert spreads == sorted(spreads)

    # Whatever the chosen magnitude, it must still rank: no collapse at production.
    production = run_real_program_fit_sweep(
        profile, programs, weights=(PROGRAM_FIT_WEIGHT,)
    )[PROGRAM_FIT_WEIGHT]
    assert production["distinct_scores"] > len(programs) * 0.75
