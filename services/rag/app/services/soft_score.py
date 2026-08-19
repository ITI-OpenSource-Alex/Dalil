import math
import re

from app.schemas.scoring import ProgramRequirements, UserProfile
from app.services.gates import comparable_gpa, degree_rank


UNKNOWN_REQUIREMENTS_SCORE = 50.0
NEUTRAL_FIT = UNKNOWN_REQUIREMENTS_SCORE / 100.0
ELIGIBILITY_POINTS = 40.0
REQUIREMENT_HEADROOM_POINTS = 15.0
SUBJECT_RELEVANCE_POINTS = 35.0
DESTINATION_POINTS = 10.0

_FIELD_OF_STUDY_TO_DISCIPLINE = (
    (
        "computer_science",
        (
            "computer",
            "software",
            "informat",
            " it",
            "data scien",
            "artificial intelligence",
            "cyber",
        ),
    ),
    ("engineering", ("engineer", "mechatron", "robotic")),
)

_TITLE_STOP_WORDS = {
    "and",
    "applied",
    "engineering",
    "master",
    "masters",
    "msc",
    "of",
    "science",
    "sciences",
    "technology",
}

_STUDY_AREA_PATTERNS = (
    ("software_engineering", ("software", "web development", "app development")),
    (
        "data_ai",
        (
            "data science",
            "data analytics",
            "artificial intelligence",
            "machine learning",
            "natural language processing",
            "business analytics",
        ),
    ),
    ("cybersecurity", ("cyber", "information security", "network security")),
    (
        "automation_control",
        (
            "automation",
            "control of complex systems",
            "control systems",
            "embedded systems",
            "signal processing",
            "telecommunication",
        ),
    ),
    ("electrical_engineering", ("electrical", "electronic", "communication technolog")),
    (
        "biomedical",
        (
            "biomedical",
            "health informatics",
            "healthcare informatics",
            "medical informatics",
            "bioinformatics",
            "computational biology",
        ),
    ),
    ("geospatial", ("geodesy", "geoinformatics", "geospatial", "geomatics")),
    (
        "computer_science",
        (
            "computer science",
            "computing science",
            "informatics",
            "information technology",
            "information systems",
            "computer and information",
        ),
    ),
    ("aerospace_engineering", ("aerospace", "aeronautic", "space engineering")),
    (
        "energy_engineering",
        ("energy engineering", "battery science", "power engineering"),
    ),
    (
        "environmental_engineering",
        ("environmental engineering", "sustainable engineering"),
    ),
    ("mechanical_engineering", ("mechanical", "mechatronic", "automotive")),
    (
        "civil_engineering",
        ("civil engineering", "structural engineering", "construction"),
    ),
    ("chemical_engineering", ("chemical engineering", "process engineering")),
    ("biotechnology", ("biotechnology", "bioengineering")),
    ("mathematical_engineering", ("mathematical engineering",)),
    ("physics", ("physics", "quantum", "materials science")),
    ("agriculture", ("agricultur", "food science", "forestry")),
    ("policy", ("policy", "politics", "public administration")),
    ("business", ("business", "management", "entrepreneurship", "finance")),
    (
        "humanities",
        ("humanities", "language technolog", "spatial planning", "animation"),
    ),
    ("general_engineering", ("engineering",)),
)


def discipline_for_field_of_study(field_of_study: str | None) -> str | None:
    """Map the profile's free-text study area to a catalogue discipline."""
    if not field_of_study or not field_of_study.strip():
        return None
    text = f" {field_of_study.strip().lower()} "
    for slug, needles in _FIELD_OF_STUDY_TO_DISCIPLINE:
        if any(needle in text for needle in needles):
            return slug
    return None


def classify_study_area(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    text = value.casefold()
    for area, needles in _STUDY_AREA_PATTERNS:
        if any(needle in text for needle in needles):
            return area
    return None


def subject_relevance(
    target_field: str | None, program_name: str | None
) -> float | None:
    """Return title-level relevance, or None when the target is unclassifiable.

    The ingestion discipline is the search bucket that discovered a record; it
    is not evidence that a title belongs to that subject. This deliberately
    derives relevance from the programme title so a contaminated Computer
    Science bucket cannot make Spatial Planning look relevant.
    """
    target_area = classify_study_area(target_field)
    if target_area is None:
        target_tokens = _meaningful_tokens(target_field)
        title_tokens = _meaningful_tokens(program_name)
        if not target_tokens:
            return None
        return 1.0 if target_tokens.intersection(title_tokens) else None

    program_area = classify_study_area(program_name)
    if program_area == target_area:
        return 1.0

    adjacent: dict[str, set[str]] = {
        "software_engineering": {"computer_science"},
        "data_ai": {"computer_science"},
        "cybersecurity": {"computer_science"},
        "computer_science": {
            "software_engineering",
            "data_ai",
            "cybersecurity",
        },
        "electrical_engineering": {"automation_control"},
        "automation_control": {"electrical_engineering"},
        "mechanical_engineering": {"aerospace_engineering"},
        "civil_engineering": {"environmental_engineering"},
        "chemical_engineering": {"biotechnology"},
        "general_engineering": {
            "electrical_engineering",
            "mechanical_engineering",
            "civil_engineering",
            "chemical_engineering",
            "aerospace_engineering",
            "energy_engineering",
            "environmental_engineering",
            "automation_control",
        },
    }
    if program_area in adjacent.get(target_area, set()):
        title = (program_name or "").casefold()
        if target_area == "electrical_engineering":
            if "embedded" in title:
                return 0.8
            if "telecommunication" in title or "signal processing" in title:
                return 0.75
            return 0.65
        if target_area == "software_engineering":
            if "information systems" in title or "information technology" in title:
                return 0.6
            return 0.75
        if target_area in {"data_ai", "cybersecurity"}:
            return 0.65
        if target_area == "computer_science":
            return 0.75
        return 0.65
    return 0.0


def normalize_gpa(gpa: float | None, scale: str) -> float:
    if gpa is None:
        return 0.0
    divisor = 100.0 if scale == "100" else 4.0
    return min(max(gpa / divisor, 0.0), 1.0)


def normalize_ielts(ielts: float | None) -> float:
    if ielts is None:
        return 0.0
    return min(max(ielts / 9.0, 0.0), 1.0)


def _ratio(value: float | int | None, required: float | int | None) -> float | None:
    if required is None or required <= 0:
        return None
    if value is None:
        return 0.0
    return min(max(float(value) / float(required), 0.0), 1.0)


def _requirement_scores(
    profile: UserProfile, program: ProgramRequirements
) -> list[float]:
    """Return coverage of the programme's published admission minimums."""
    dimensions: list[float] = []

    for value, required in (
        (profile.ieltsScore, program.min_ielts),
        (
            comparable_gpa(profile.gpa, profile.gpaScale, program.min_gpa),
            program.min_gpa,
        ),
        (profile.ects, program.min_ects),
        (profile.workExperienceYears, program.min_work_experience),
    ):
        score = _ratio(value, required)
        if score is not None:
            dimensions.append(score)

    if program.degree_level:
        programme = degree_rank(program.degree_level)
        holder = degree_rank(profile.degreeLevel)
        dimensions.append(
            1.0
            if programme is None or (holder is not None and holder >= programme - 1)
            else 0.0
        )

    if program.required_citizenship:
        dimensions.append(
            1.0 if profile.citizenship == program.required_citizenship else 0.0
        )

    return dimensions


def requirement_summary(
    profile: UserProfile, program: ProgramRequirements
) -> tuple[int, int]:
    scores = _requirement_scores(profile, program)
    return len(scores), sum(1 for score in scores if score >= 1.0)


def _headroom(value: float | int | None, required: float | int | None, scale: float):
    """Smoothly reward margin above a minimum without creating a second gate."""
    if required is None or required <= 0:
        return None
    if value is None or value <= required:
        return 0.0
    return 1.0 - math.exp(-(float(value) - float(required)) / scale)


def _requirement_headroom(
    profile: UserProfile, program: ProgramRequirements
) -> tuple[float | None, int]:
    comparable = comparable_gpa(profile.gpa, profile.gpaScale, program.min_gpa)
    gpa_scale = 12.5 if program.min_gpa and program.min_gpa > 4 else 0.5
    dimensions = [
        _headroom(profile.ieltsScore, program.min_ielts, 0.75),
        _headroom(comparable, program.min_gpa, gpa_scale),
        _headroom(profile.ects, program.min_ects, 30.0),
        _headroom(
            profile.workExperienceYears,
            program.min_work_experience,
            1.5,
        ),
    ]
    published = [value for value in dimensions if value is not None]
    if not published:
        return None, 0
    return sum(published) / len(published), len(published)


def _meaningful_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _TITLE_STOP_WORDS
    }


def _target_field(profile: UserProfile) -> str | None:
    return profile.targetFieldOfStudy or profile.fieldOfStudy


def _destination_alignment(profile: UserProfile, program: ProgramRequirements) -> float:
    if not profile.targetCountries or not program.country:
        return NEUTRAL_FIT
    wanted = {country.casefold() for country in profile.targetCountries}
    return float(program.country.casefold() in wanted)


def compute_score_breakdown(profile: UserProfile, program: ProgramRequirements) -> dict:
    """Explain the deterministic fit score used for ranking.

    Admission minimums are pass/fail. Once they are met, academic margin and
    explicit preferences add ranking resolution. Unpublished numeric fields are
    excluded and reported as limited evidence instead of becoming zeroes.
    """
    requirement_scores = _requirement_scores(profile, program)
    evaluated = len(requirement_scores)
    met = sum(score >= 1.0 for score in requirement_scores)
    relevance = subject_relevance(_target_field(profile), program.name)
    subject_points = round(
        (NEUTRAL_FIT if relevance is None else relevance) * SUBJECT_RELEVANCE_POINTS,
        2,
    )
    destination_points = round(
        _destination_alignment(profile, program) * DESTINATION_POINTS,
        2,
    )

    if not requirement_scores:
        return {
            "eligibility_points": 0.0,
            "requirement_headroom_points": None,
            "subject_points": subject_points,
            "destination_points": destination_points,
            "headroom_dimensions_evaluated": 0,
            "confidence": "insufficient",
            "subject_relevance": relevance,
            "total": UNKNOWN_REQUIREMENTS_SCORE,
        }

    if met < evaluated:
        total = min(39.0, (sum(requirement_scores) / evaluated) * 39.0)
        return {
            "eligibility_points": round(total, 2),
            "requirement_headroom_points": 0.0,
            "subject_points": subject_points,
            "destination_points": destination_points,
            "headroom_dimensions_evaluated": 0,
            "confidence": "blocked",
            "subject_relevance": relevance,
            "total": round(total, 2),
        }

    headroom, headroom_dimensions = _requirement_headroom(profile, program)
    headroom_points = (
        None if headroom is None else round(headroom * REQUIREMENT_HEADROOM_POINTS, 2)
    )
    total = (
        ELIGIBILITY_POINTS
        + (headroom_points or 0.0)
        + subject_points
        + destination_points
    )
    return {
        "eligibility_points": ELIGIBILITY_POINTS,
        "requirement_headroom_points": headroom_points,
        "subject_points": subject_points,
        "destination_points": destination_points,
        "headroom_dimensions_evaluated": headroom_dimensions,
        "confidence": "standard" if headroom_dimensions else "limited",
        "subject_relevance": relevance,
        "total": round(min(total, 100.0), 2),
    }


def compute_program_fit(profile: UserProfile, program: ProgramRequirements) -> float:
    return compute_score_breakdown(profile, program)["total"] / 100.0


def compute_soft_score(profile: UserProfile, program: ProgramRequirements) -> float:
    return compute_score_breakdown(profile, program)["total"]
