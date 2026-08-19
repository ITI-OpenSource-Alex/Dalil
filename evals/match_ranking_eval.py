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


# ---------------------------------------------------------------------------
# Sweep against the PRODUCTION scorer.
#
# The sweep above scores `calculate_mock_soft_score`, a toy function that shares
# nothing with services/rag/app/services/soft_score.py beyond the name of one
# constant. Whatever weight it favours says nothing about the weight the product
# actually uses, so it cannot satisfy "PROGRAM_FIT_WEIGHT chosen from the sweep".
#
# The hard part is ground truth: any hand-written "correct" ranking would encode
# invented preferences and then measure how well the scorer reproduces them. So
# this sweep only asserts orderings that follow from DOMINANCE — program A ranks
# above B for a profile if the profile clears A by at least as much on every stated
# requirement and strictly more on one. That is objective, and it is the property a
# ranking must have to be defensible at all.
#
# Discrimination is reported alongside it, because the failure this constant exists
# to prevent was not mis-ordering, it was every program scoring the same.
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = (0.0, 0.15, 0.25, 0.35, 0.5, 0.65, 0.8)


def _dominance_pairs(profile, programs, clearance) -> List[Tuple[str, str]]:
    """(better_id, worse_id) pairs where one program is unambiguously the better fit."""
    pairs = []
    for a in programs:
        for b in programs:
            if a.id == b.id:
                continue
            margins_a, margins_b = clearance(profile, a), clearance(profile, b)
            shared = set(margins_a) & set(margins_b)
            if not shared:
                continue
            if all(margins_a[k] >= margins_b[k] for k in shared) and \
               any(margins_a[k] > margins_b[k] for k in shared):
                pairs.append((a.id, b.id))
    return pairs


def run_real_program_fit_sweep(profile, programs, weights=DEFAULT_WEIGHTS) -> Dict[float, Dict[str, Any]]:
    """Sweep PROGRAM_FIT_WEIGHT through the real compute_soft_score.

    Returns, per weight: the share of dominance pairs ordered correctly, the number
    of distinct scores produced, and the spread between best and worst.
    """
    from app.services import soft_score as ss

    def clearance(prof, prog):
        """Per-dimension surplus over each requirement the program actually states."""
        margins = {}
        if prog.min_ielts is not None and prof.ieltsScore is not None:
            margins["ielts"] = prof.ieltsScore - prog.min_ielts
        if prog.min_gpa is not None and prof.gpa is not None:
            margins["gpa"] = ss.normalize_gpa(prof.gpa, prof.gpaScale) - \
                             ss.normalize_gpa(prog.min_gpa, prof.gpaScale)
        if prog.min_ects is not None and prof.ects is not None:
            margins["ects"] = prof.ects - prog.min_ects
        if prog.min_work_experience is not None:
            margins["work"] = prof.workExperienceYears - prog.min_work_experience
        return margins

    pairs = _dominance_pairs(profile, programs, clearance)
    original = ss.PROGRAM_FIT_WEIGHT
    results: Dict[float, Dict[str, Any]] = {}
    try:
        for weight in weights:
            ss.PROGRAM_FIT_WEIGHT = weight
            scores = {p.id: ss.compute_soft_score(profile, p) for p in programs}
            correct = sum(1 for better, worse in pairs if scores[better] > scores[worse])
            values = list(scores.values())
            results[weight] = {
                "dominance_accuracy": round(correct / len(pairs), 4) if pairs else None,
                "dominance_pairs": len(pairs),
                "distinct_scores": len(set(round(v, 4) for v in values)),
                "programs": len(values),
                "spread": round(max(values) - min(values), 4) if values else 0.0,
            }
    finally:
        ss.PROGRAM_FIT_WEIGHT = original
    return results
