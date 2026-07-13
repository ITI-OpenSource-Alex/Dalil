from app.schemas.scoring import UserProfile, ProgramRequirements
from app.services.soft_score import normalize_gpa, normalize_ielts, compute_soft_score


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


def test_compute_soft_score_perfect():
    profile = UserProfile(
        userId="1",
        gpa=4.0,
        gpaScale="4.0",
        ieltsScore=9.0,
        workExperienceYears=10,
        extracurricularsScore=10,
    )
    program = ProgramRequirements(id="p1")
    score = compute_soft_score(profile, program)
    assert score == 100.0


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
