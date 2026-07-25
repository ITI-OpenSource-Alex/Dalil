import math
from typing import List, Dict, Tuple, Any

def compute_ndcg(actual_ranks: List[str], expected_ranks: List[str]) -> float:
    """Compute normalized Discounted Cumulative Gain (nDCG) for ranking comparison."""
    if not actual_ranks or not expected_ranks:
        return 0.0
    
    # Map item ID to relevance score (higher for items expected earlier)
    n = len(expected_ranks)
    rel_map = {item_id: (n - idx) for idx, item_id in enumerate(expected_ranks)}

    dcg = 0.0
    for idx, item_id in enumerate(actual_ranks):
        rel = rel_map.get(item_id, 0)
        dcg += (2**rel - 1) / math.log2(idx + 2)

    idcg = 0.0
    for idx, item_id in enumerate(expected_ranks):
        rel = rel_map[item_id]
        idcg += (2**rel - 1) / math.log2(idx + 2)

    return round(dcg / idcg, 4) if idcg > 0 else 0.0

def calculate_mock_soft_score(profile: dict, program: dict, fit_weight: float) -> float:
    """Deterministic soft score calculation combining absolute user strength and program fit."""
    user_strength = (profile.get("gpa", 3.0) / 4.0) * 50.0 + (profile.get("ielts", 6.5) / 9.0) * 50.0
    
    # Program fit: match degree and country
    degree_fit = 100.0 if profile.get("degree") == program.get("degree") else 50.0
    country_fit = 100.0 if program.get("country") in profile.get("target_countries", []) else 40.0
    program_fit = (degree_fit + country_fit) / 2.0

    return (1.0 - fit_weight) * user_strength + fit_weight * program_fit

def run_program_fit_weight_sweep(
    profiles: List[dict],
    programs: List[dict],
    expected_order: List[str],
    weights: List[float] = [0.35, 0.50, 0.65, 0.80]
) -> Dict[float, float]:
    """Run deterministic sweep over PROGRAM_FIT_WEIGHT values and return nDCG score curve."""
    results = {}
    
    for weight in weights:
        # Score each program for the primary profile
        scored_programs = []
        for prog in programs:
            score = calculate_mock_soft_score(profiles[0], prog, weight)
            scored_programs.append((prog["id"], score))
            
        # Sort descending by score
        scored_programs.sort(key=lambda x: x[1], reverse=True)
        actual_order = [p[0] for p in scored_programs]
        
        ndcg = compute_ndcg(actual_order, expected_order)
        results[weight] = ndcg
        
    return results
