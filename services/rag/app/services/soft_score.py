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


# How much of the final score reflects fit with *this* program rather than the
# candidate's absolute strength. Stage 1 already removed the disqualifying programs
# and Stage 3's LLM boost was removed from /match by GOA-125, so without this the
# score is identical for every program a user passes — a "ranked" list that isn't.
PROGRAM_FIT_WEIGHT = 0.35

# A requirement the program does not state cannot count for or against fit.
NEUTRAL_FIT = 0.5

# Scale at which a surplus counts as "comfortably clear" per dimension. This is a
# soft scale, not a ceiling: fit approaches 1.0 asymptotically and never pins there.
#
# The previous hard cap (min(surplus / headroom, 1.0)) made every comfortably-cleared
# requirement score identically. That was invisible at ~100 programs and obvious at
# 1,333: the entire top-10 tied at 83.46 because they had all saturated. Ranking has
# to keep discriminating at the top of a large candidate set, which is exactly where
# it matters most.
_FIT_SCALE = {"ielts": 1.5, "gpa": 1.0, "ects": 60, "work": 3}

# How much of program fit comes from *how many* of its stated requirements we could
# actually check, rather than from the margins alone. A program stating IELTS, GPA and
# ECTS that the profile clears is a better-evidenced match than one stating a single
# ECTS minimum — we verified more of it. This also breaks ties on match quality rather
# than on something unrelated to the profile.
COVERAGE_WEIGHT = 0.25

# Requirement dimensions a program can state, used as the denominator for coverage.
JUDGEABLE_DIMENSIONS = 4


def _margin_fit(profile_value: float | None, required: float | None, scale: float) -> float | None:
    """Fit for one requirement: how comfortably the profile clears it.

    Returns None when the dimension cannot be judged (program states no requirement,
    or the profile lacks the value) so the caller can leave it out of the average
    instead of scoring an unknown as a zero. Most real MastersPortal programs publish
    no GPA or ECTS requirement, so treating absence as failure would flatten the
    ranking just as badly as ignoring the program entirely.

    0.5 means "exactly meets"; above means margin to spare; below means short of the
    requirement but not disqualified (hard gates own disqualification).

    Above the requirement the curve is surplus / (surplus + scale) — diminishing
    returns without a ceiling, so clearing IELTS 5.5 with a 7.0 still outranks clearing
    IELTS 6.5 with the same 7.0, however large the catalog gets.
    """
    if required is None or profile_value is None:
        return None
    if required <= 0:
        # "Requires 0 years of experience" is the absence of a requirement, not a
        # requirement that is exactly met. Scoring it NEUTRAL_FIT dragged down the
        # average of programs that were explicit about requiring nothing, ranking them
        # below programs that simply left the field blank.
        return None
    if profile_value >= required:
        surplus = profile_value - required
        if not scale:
            return NEUTRAL_FIT
        return NEUTRAL_FIT + NEUTRAL_FIT * (surplus / (surplus + scale))
    return NEUTRAL_FIT * max(profile_value / required, 0.0)


def compute_program_fit(profile: UserProfile, program: ProgramRequirements) -> float:
    """Average fit across the requirements this program actually states (0.0-1.0).

    Programs stating nothing score NEUTRAL_FIT, so they rank on candidate strength
    alone rather than being pushed to the top or bottom of the list.
    """
    dimensions = [
        _margin_fit(profile.ieltsScore, program.min_ielts, _FIT_SCALE["ielts"]),
        _margin_fit(profile.gpa, program.min_gpa, _FIT_SCALE["gpa"]),
        _margin_fit(profile.ects, program.min_ects, _FIT_SCALE["ects"]),
        _margin_fit(
            profile.workExperienceYears, program.min_work_experience, _FIT_SCALE["work"]
        ),
    ]
    judged = [d for d in dimensions if d is not None]
    if not judged:
        return NEUTRAL_FIT

    margin_fit = sum(judged) / len(judged)

    # Blend in how much of the program we could actually verify. Two programs whose
    # margins average the same are not equally good matches if one was checked on
    # three requirements and the other on one.
    coverage = len(judged) / JUDGEABLE_DIMENSIONS
    return margin_fit * (1 - COVERAGE_WEIGHT) + coverage * COVERAGE_WEIGHT


def compute_soft_score(profile: UserProfile, program: ProgramRequirements) -> float:
    """
    Computes a weighted soft score out of 100, blending the candidate's absolute
    strength with how well they fit *this specific* program.
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

    candidate_strength = (
        (norm_gpa * weight_gpa)
        + (norm_ielts * weight_ielts)
        + (norm_work * weight_work)
        + (norm_extra * weight_extra)
    )

    # 3. Blend in program fit so two programs a user qualifies for can rank differently.
    program_fit = compute_program_fit(profile, program)
    total = (
        candidate_strength * (1.0 - PROGRAM_FIT_WEIGHT)
        + program_fit * PROGRAM_FIT_WEIGHT
    )
    return round(min(max(total, 0.0), 1.0) * 100.0, 2)
