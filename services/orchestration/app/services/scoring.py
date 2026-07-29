"""
Opportunity Scoring — GOA-060

Pure-function scoring logic for ranking study-abroad opportunities.

Key rule:  real IELTS bands from the Exam Service **always** override
self-reported bands when both are present for the same skill.
"""

from typing import Dict, Optional

import structlog

logger = structlog.get_logger("orchestration.scoring")

# Skills the scoring engine recognises (IELTS band descriptors)
IELTS_SKILLS = ("reading", "listening", "writing", "speaking")


def merge_bands(
    self_reported: Dict[str, float],
    real_exam_bands: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Merge self-reported and real exam bands.

    Real exam bands **explicitly override** self-reported values for the
    same skill.  Self-reported values are kept only for skills that have
    no real exam data.

    Returns:
        A new dict mapping skill → band (float).
    """
    merged = dict(self_reported)
    if real_exam_bands:
        for skill, band in real_exam_bands.items():
            if band is not None:
                merged[skill] = band
    return merged


def compute_opportunity_score(
    self_reported_bands: Dict[str, float],
    program_requirements: Dict[str, float],
    real_exam_bands: Optional[Dict[str, float]] = None,
) -> float:
    """
    Score a programme opportunity against the user's IELTS profile.

    Args:
        self_reported_bands:  User-declared bands, e.g. ``{"reading": 5.0}``.
        program_requirements: Minimum bands the programme demands per skill,
                              e.g. ``{"reading": 6.5, "listening": 6.0}``.
        real_exam_bands:      Verified bands from the Exam Service.  When
                              present for a skill they **override** the
                              self-reported value.

    Returns:
        A float in **[0.0, 1.0]** representing the fit:
            1.0  →  meets or exceeds every required band
            0.0  →  no band data at all
        Each skill contributes equally (simple average of per-skill ratios,
        each ratio capped at 1.0 so exceeding a requirement doesn't inflate
        the score above 1.0).
    """
    bands = merge_bands(self_reported_bands, real_exam_bands)

    if not program_requirements:
        return 1.0  # no requirements → automatic fit

    skill_scores = []
    for skill, required in program_requirements.items():
        user_band = bands.get(skill)
        if user_band is None or required <= 0:
            skill_scores.append(0.0)
            continue
        ratio = min(user_band / required, 1.0)
        skill_scores.append(ratio)

    if not skill_scores:
        return 0.0

    score = sum(skill_scores) / len(skill_scores)

    logger.debug(
        "Opportunity score computed",
        self_reported=self_reported_bands,
        real_exam=real_exam_bands,
        merged=bands,
        requirements=program_requirements,
        score=round(score, 4),
    )
    return round(score, 4)
