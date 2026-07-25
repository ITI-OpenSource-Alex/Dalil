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
