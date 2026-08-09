from app.schemas.scoring import ProgramRequirements, UserProfile
from app.services.soft_score import (
    NEUTRAL_FIT,
    compute_program_fit,
    compute_score_breakdown,
    compute_soft_score,
    normalize_gpa,
    normalize_ielts,
    subject_relevance,
)


def test_normalizers_remain_bounded():
    assert normalize_gpa(85.0, "100") == 0.85
    assert normalize_gpa(4.5, "4.0") == 1.0
    assert normalize_ielts(9.5) == 1.0


def test_meeting_every_published_requirement_establishes_eligibility_not_perfection():
    profile = UserProfile(
        userId="1",
        degreeLevel="Bachelor",
        gpa=3.2,
        gpaScale="4.0",
        ieltsScore=6.5,
        ects=180,
        workExperienceYears=2,
    )
    program = ProgramRequirements(
        id="p1",
        degree_level="Master",
        min_gpa=3.2,
        min_ielts=6.5,
        min_ects=180,
        min_work_experience=2,
    )
    assert compute_program_fit(profile, program) == 0.625
    assert compute_soft_score(profile, program) == 62.5


def test_a_failed_requirement_stays_below_the_eligible_score_range():
    profile = UserProfile(userId="1", ieltsScore=6.0)
    program = ProgramRequirements(id="p1", min_ielts=8.0)
    assert compute_soft_score(profile, program) == 29.25


def test_cross_scale_gpa_is_compared_on_program_scale():
    profile = UserProfile(userId="1", gpa=80, gpaScale="100")
    program = ProgramRequirements(id="p1", min_gpa=3.2)
    assert compute_soft_score(profile, program) == 62.5


def test_unpublished_requirements_are_insufficient_data_not_candidate_failure():
    profile = UserProfile(userId="1", gpa=4.0, ieltsScore=9.0)
    program = ProgramRequirements(id="p1")
    assert compute_program_fit(profile, program) == NEUTRAL_FIT
    assert compute_soft_score(profile, program) == 50.0


def test_missing_required_profile_value_scores_that_requirement_zero():
    profile = UserProfile(userId="1")
    program = ProgramRequirements(id="p1", min_ielts=6.5, min_ects=120)
    assert compute_soft_score(profile, program) == 0.0


def test_score_stays_within_bounds():
    for score in (
        compute_soft_score(UserProfile(userId="1"), ProgramRequirements(id="a")),
        compute_soft_score(
            UserProfile(userId="1", ieltsScore=9),
            ProgramRequirements(id="b", min_ielts=1),
        ),
    ):
        assert 0.0 <= score <= 100.0


def test_requirement_headroom_creates_resolution_between_eligible_candidates():
    exact = UserProfile(userId="1", ieltsScore=6.5, ects=120)
    stronger = UserProfile(userId="1", ieltsScore=7.5, ects=180)
    program = ProgramRequirements(id="p1", min_ielts=6.5, min_ects=120)

    assert compute_soft_score(stronger, program) > compute_soft_score(exact, program)
    breakdown = compute_score_breakdown(stronger, program)
    assert breakdown["eligibility_points"] == 40.0
    assert 0 < breakdown["requirement_headroom_points"] < 15
    assert breakdown["headroom_dimensions_evaluated"] == 2


def test_country_and_subject_are_independent_high_weight_components():
    profile = UserProfile(
        userId="1",
        degreeLevel="Bachelor",
        targetCountries=["Germany"],
        fieldOfStudy="Computer Science",
    )
    program = ProgramRequirements(
        id="p1",
        name="MSc Computer Science",
        country="Germany",
        discipline="computer_science",
        degree_level="Master",
    )

    breakdown = compute_score_breakdown(profile, program)
    assert breakdown["subject_points"] == 35.0
    assert breakdown["destination_points"] == 10.0
    assert breakdown["confidence"] == "limited"


def test_unpublished_numeric_criteria_are_marked_limited_not_zeroed():
    profile = UserProfile(userId="1", degreeLevel="Bachelor")
    program = ProgramRequirements(id="p1", degree_level="Master")

    breakdown = compute_score_breakdown(profile, program)
    assert breakdown["requirement_headroom_points"] is None
    assert breakdown["headroom_dimensions_evaluated"] == 0
    assert breakdown["confidence"] == "limited"


def test_software_engineering_title_relevance_rejects_unrelated_bucket_noise():
    assert subject_relevance("Software Engineering", "MSc Software Engineering") == 1.0
    assert subject_relevance("Software Engineering", "Computer Science") == 0.75
    for unrelated in (
        "Spatial Planning",
        "Agricultural Science and Technology",
        "Physics (Condensed Matter Physics)",
        "Politics and Technology",
        "Data Science and AI for Business",
        "Medical Informatics",
        "Healthcare Informatics",
        "Bioinformatics and Computational Biology",
        "Geodesy and Geoinformatics",
    ):
        assert subject_relevance("Software Engineering", unrelated) == 0.0


def test_intended_field_overrides_undergraduate_field_for_subject_fit():
    profile = UserProfile(
        userId="1",
        fieldOfStudy="Mechanical Engineering",
        targetFieldOfStudy="Software Engineering",
        degreeLevel="Bachelor",
    )
    software = ProgramRequirements(
        id="software",
        name="Software Engineering",
        degree_level="Master",
    )
    mechanical = ProgramRequirements(
        id="mechanical",
        name="Mechanical Engineering",
        degree_level="Master",
    )

    assert compute_score_breakdown(profile, software)["subject_relevance"] == 1.0
    assert compute_score_breakdown(profile, mechanical)["subject_relevance"] == 0.0


def test_electrical_engineering_does_not_treat_every_engineering_title_as_related():
    assert subject_relevance("Electrical Engineering", "Electronic Engineering") == 1.0
    assert (
        subject_relevance(
            "Electrical Engineering",
            "Automation Engineering and Control of Complex Systems",
        )
        == 0.65
    )
    for unrelated in (
        "Aerospace Engineering",
        "Civil Systems Engineering",
        "Environmental Engineering",
        "Energy Engineering",
        "Mathematical Engineering",
        "Industrial Biotechnology and Bioengineering",
        "Battery Science and Technology in Engineering",
    ):
        assert subject_relevance("Electrical Engineering", unrelated) == 0.0


def test_subject_weight_creates_material_score_separation():
    profile = UserProfile(
        userId="1",
        targetFieldOfStudy="Electrical Engineering",
        targetCountries=["Germany"],
        degreeLevel="Bachelor",
        ieltsScore=7.5,
    )

    def score(name: str) -> float:
        return compute_soft_score(
            profile,
            ProgramRequirements(
                id=name,
                name=name,
                country="Germany",
                degree_level="Master",
                min_ielts=6.5,
            ),
        )

    exact = score("Electronic Engineering")
    embedded = score("Embedded Systems")
    automation = score("Automation Engineering and Control of Complex Systems")

    assert exact - embedded >= 5
    assert embedded - automation >= 3
