from app.schemas.scoring import UserProfile, ProgramRequirements


def normalize_gpa(gpa: float | None, scale: str) -> float:
    if gpa is None:
        return 0.0
    if scale == "100":
        return min(max(gpa / 100.0, 0.0), 1.0)

    # Default to standard 4.0 scale
    return min(max(gpa / 4.0, 0.0), 1.0)


def normalize_ielts(ielts: float | None) -> float:
    if ielts is None:
        return 0.0
    return min(max(ielts / 9.0, 0.0), 1.0)


def normalize_work_experience(years: int) -> float:
    # Cap at 10 years of experience for scoring purposes
    return min(max(years / 10.0, 0.0), 1.0)


def normalize_extracurriculars(score: int) -> float:
    # Score is explicitly 0-10 based on our Postgres CHECK constraint
    return min(max(score / 10.0, 0.0), 1.0)


def compute_soft_score(profile: UserProfile, program: ProgramRequirements) -> float:
    """
    Computes a weighted soft score out of 100.
    Returns a float between 0.0 and 100.0.
    """

    # 1. Normalize all inputs to 0.0 - 1.0
    norm_gpa = normalize_gpa(profile.gpa, profile.gpaScale)
    norm_ielts = normalize_ielts(profile.ieltsScore)
    norm_work = normalize_work_experience(profile.workExperienceYears)
    norm_extra = normalize_extracurriculars(profile.extracurricularsScore)

    # 2. Apply static heuristics weights (Must sum to 1.0)
    weight_gpa = 0.40
    weight_ielts = 0.20
    weight_work = 0.20
    weight_extra = 0.20

    total = (
        (norm_gpa * weight_gpa)
        + (norm_ielts * weight_ielts)
        + (norm_work * weight_work)
        + (norm_extra * weight_extra)
    )
    return round(total * 100.0, 2)
