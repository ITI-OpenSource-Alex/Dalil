from app.schemas.scoring import UserProfile, ProgramRequirements
from app.services.soft_score import (
    NEUTRAL_FIT,
    compute_program_fit,
    compute_soft_score,
    normalize_gpa,
    normalize_ielts,
)


def test_normalize_gpa_4_scale():
    assert normalize_gpa(4.0, "4.0") == 1.0
    assert normalize_gpa(2.0, "4.0") == 0.5
    assert normalize_gpa(4.5, "4.0") == 1.0  # Clamped
    assert normalize_gpa(None, "4.0") == 0.0


def test_normalize_gpa_100_scale():
    assert normalize_gpa(100.0, "100") == 1.0
    assert normalize_gpa(85.0, "100") == 0.85


def test_normalize_ielts():
    assert normalize_ielts(9.0) == 1.0
    assert normalize_ielts(4.5) == 0.5
    assert normalize_ielts(None) == 0.0


PERFECT_PROFILE = dict(
    gpa=4.0, gpaScale="4.0", ieltsScore=9.0, workExperienceYears=10, extracurricularsScore=10
)


def test_perfect_candidate_at_requirementless_program_is_capped():
    """A program publishing no requirements cannot demonstrate fit, so its fit term
    is NEUTRAL_FIT (0.5): 1.0 * 0.65 + 0.5 * 0.35 = 0.825.

    Before program fit existed this returned 100.0 for every program alike — which is
    exactly why /match returned 46 identically-scored "ranked" results."""
    profile = UserProfile(userId="1", **PERFECT_PROFILE)
    program = ProgramRequirements(id="p1")
    assert compute_soft_score(profile, program) == 82.5


def test_100_is_reachable_when_all_stated_requirements_are_cleared():
    """100 now means: a perfect candidate who comfortably clears everything this
    program actually asks for."""
    profile = UserProfile(userId="1", ects=180, **PERFECT_PROFILE)
    program = ProgramRequirements(
        id="p1", min_ielts=6.0, min_gpa=3.0, min_ects=120, min_work_experience=1
    )
    assert compute_soft_score(profile, program) == 100.0


def test_two_programs_the_user_qualifies_for_score_differently():
    """The point of the change: gate-passing programs must be orderable."""
    profile = UserProfile(userId="1", gpa=3.5, gpaScale="4.0", ieltsScore=7.0,
                          workExperienceYears=2, extracurricularsScore=5)
    easy = compute_soft_score(profile, ProgramRequirements(id="easy", min_ielts=5.5))
    tight = compute_soft_score(profile, ProgramRequirements(id="tight", min_ielts=7.0))
    assert easy > tight, (easy, tight)


def test_unjudgeable_dimensions_are_excluded_not_scored_zero():
    """Most real MastersPortal programs publish no GPA/ECTS requirement. Scoring
    those as zeros would flatten the ranking as badly as ignoring the program."""
    profile = UserProfile(userId="1", gpa=3.5, gpaScale="4.0", ieltsScore=7.0)
    only_ielts = compute_program_fit(profile, ProgramRequirements(id="a", min_ielts=6.0))
    plus_unstated = compute_program_fit(
        profile, ProgramRequirements(id="b", min_ielts=6.0, min_work_experience=None)
    )
    assert only_ielts == plus_unstated


def test_fit_neutral_when_nothing_judgeable():
    profile = UserProfile(userId="1", gpa=3.5, gpaScale="4.0", ieltsScore=7.0)
    assert compute_program_fit(profile, ProgramRequirements(id="x")) == NEUTRAL_FIT


def test_exactly_meeting_a_requirement_is_neutral():
    profile = UserProfile(userId="1", ieltsScore=6.5)
    assert compute_program_fit(
        profile, ProgramRequirements(id="p", min_ielts=6.5)
    ) == NEUTRAL_FIT


def test_below_requirement_is_under_neutral_but_not_zero():
    """Hard gates own disqualification; the soft score only expresses degree."""
    profile = UserProfile(userId="1", ieltsScore=5.0)
    fit = compute_program_fit(profile, ProgramRequirements(id="p", min_ielts=6.5))
    assert 0.0 < fit < NEUTRAL_FIT


def test_score_stays_within_bounds():
    for gpa, ielts in ((0.0, 0.0), (4.0, 9.0), (2.0, 5.0)):
        profile = UserProfile(userId="1", gpa=gpa, gpaScale="4.0", ieltsScore=ielts)
        for program in (ProgramRequirements(id="a"),
                        ProgramRequirements(id="b", min_ielts=9.0, min_gpa=4.0)):
            assert 0.0 <= compute_soft_score(profile, program) <= 100.0


def test_compute_soft_score_partial():
    profile = UserProfile(
        userId="1",
        gpa=2.0,  # 0.5 * 0.40 = 0.20
        gpaScale="4.0",
        ieltsScore=4.5,  # 0.5 * 0.20 = 0.10
        workExperienceYears=5,  # 0.5 * 0.20 = 0.10
        extracurricularsScore=5,  # 0.5 * 0.20 = 0.10
    )
    program = ProgramRequirements(id="p1")
    score = compute_soft_score(profile, program)
    # Total should be exactly 50.0
    assert score == 50.0
