"""GOA-064: deterministic grading checks against independent answer-key fixtures."""

import json
from pathlib import Path

import pytest

from app.services.grading_service import GradingService


SERVICE_ROOT = Path(__file__).resolve().parents[1]
HOST_FIXTURE_DIR = SERVICE_ROOT.parents[1] / "evals" / "exam_answer_keys" if len(SERVICE_ROOT.parents) > 1 else Path("/__missing__")
FIXTURE_DIR = HOST_FIXTURE_DIR if HOST_FIXTURE_DIR.exists() else Path("/evals/exam_answer_keys")
READING_FIXTURE = FIXTURE_DIR / "cambridge_ielts_17_reading.json"
LISTENING_FIXTURE = FIXTURE_DIR / "cambridge_ielts_15_listening.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_cases(path: Path) -> list[tuple[str, dict]]:
    payload = _load(path)
    return [(test_number, test) for test_number, test in payload["tests"].items()]


def _correct_submission(answers: dict) -> dict:
    """Represent a candidate response using one accepted value per question."""
    return {
        question: value[0] if isinstance(value, list) else value
        for question, value in answers.items()
    }


@pytest.mark.parametrize("test_number,test", _fixture_cases(READING_FIXTURE), ids=lambda value: str(value))
def test_perfect_reading_submission_scores_all_questions(test_number: str, test: dict) -> None:
    result = GradingService().grade_reading(_correct_submission(test["answers"]), test)

    assert result["raw_score"] == 40, f"IELTS17 Reading Test {test_number}"
    assert result["band_score"] == 9.0


@pytest.mark.parametrize("test_number,test", _fixture_cases(LISTENING_FIXTURE), ids=lambda value: str(value))
def test_perfect_listening_submission_scores_all_questions(test_number: str, test: dict) -> None:
    result = GradingService().grade_listening(_correct_submission(test["answers"]), test)

    assert result["raw_score"] == 40, f"IELTS15 Listening Test {test_number}"
    assert result["band_score"] == 9.0


@pytest.mark.parametrize(
    ("fixture_path", "test_number", "skill", "expected_score"),
    [
        (READING_FIXTURE, "1", "reading", 13),
        (READING_FIXTURE, "2", "reading", 20),
        (LISTENING_FIXTURE, "1", "listening", 10),
        (LISTENING_FIXTURE, "2", "listening", 30),
    ],
)
def test_known_partial_submissions_have_exact_raw_scores(
    fixture_path: Path,
    test_number: str,
    skill: str,
    expected_score: int,
) -> None:
    answers = _load(fixture_path)["tests"][test_number]["answers"]
    submitted = {
        question: answer
        for question, answer in _correct_submission(answers).items()
        if int(question) <= expected_score
    }
    answer_key = _load(fixture_path)["tests"][test_number]
    grader = GradingService()
    result = grader.grade_reading(submitted, answer_key) if skill == "reading" else grader.grade_listening(submitted, answer_key)

    assert result["raw_score"] == expected_score


@pytest.mark.parametrize(
    ("exam_type", "raw_score", "expected_band"),
    [
        ("academic", 0, 0.0), ("academic", 10, 4.0), ("academic", 20, 5.5),
        ("academic", 30, 7.0), ("academic", 35, 8.0), ("academic", 39, 9.0), ("academic", 40, 9.0),
        ("general", 0, 0.0), ("general", 10, 3.0), ("general", 20, 4.5),
        ("general", 30, 6.0), ("general", 35, 7.0), ("general", 39, 8.5), ("general", 40, 9.0),
    ],
)
def test_published_reading_band_examples(exam_type: str, raw_score: int, expected_band: float) -> None:
    key = {str(question): f"answer-{question}" for question in range(1, 41)}
    submitted = {question: value for question, value in key.items() if int(question) <= raw_score}

    result = GradingService().grade_reading(submitted, key, exam_type=exam_type)

    assert result["raw_score"] == raw_score
    assert result["band_score"] == expected_band


@pytest.mark.parametrize(
    ("table_name", "band_table"),
    [
        ("academic", GradingService.READING_ACADEMIC_BAND_BY_RAW_SCORE),
        ("general", GradingService.READING_GENERAL_BAND_BY_RAW_SCORE),
        ("listening", GradingService.LISTENING_BAND_BY_RAW_SCORE),
    ],
)
def test_every_band_boundary_is_exercised_from_both_sides(table_name: str, band_table: tuple[tuple[int, float], ...]) -> None:
    grader = GradingService()
    for minimum, band in band_table:
        assert grader._lookup_band(minimum, band_table) == band, table_name
        if minimum > 0:
            assert grader._lookup_band(minimum - 1, band_table) != band, table_name


def test_listening_boundaries_and_zero_are_deterministic() -> None:
    key = {str(question): f"answer-{question}" for question in range(1, 41)}
    grader = GradingService()

    for raw_score, expected_band in ((0, 0.0), (10, 4.0), (20, 5.5), (30, 7.0), (35, 8.0), (39, 9.0), (40, 9.0)):
        submitted = {question: value for question, value in key.items() if int(question) <= raw_score}
        result = grader.grade_listening(submitted, key)
        assert (result["raw_score"], result["band_score"]) == (raw_score, expected_band)


def test_not_given_is_not_false() -> None:
    result = GradingService().grade_reading(
        {"1": "NOT GIVEN", "2": "FALSE"},
        {"1": "FALSE", "2": "NOT GIVEN"},
    )

    assert result["raw_score"] == 0


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [("PART TIME", ["part-time", "part time"]), ("colour", ["color", "colour"]), ("NESTS", ["nest", "nests"])],
)
def test_fill_blank_answers_are_case_insensitive_and_accept_alternatives(submitted: str, expected: list[str]) -> None:
    result = GradingService().grade_reading({"1": submitted}, {"1": expected})

    assert result["raw_score"] == 1


@pytest.mark.parametrize(
    ("fixture_path", "book_ref", "skill", "test_number"),
    [
        (READING_FIXTURE, "IELTS17", "reading", str(number)) for number in range(1, 5)
    ]
    + [
        (LISTENING_FIXTURE, "IELTS15", "listening", str(number)) for number in range(1, 5)
    ],
)
@pytest.mark.xfail(strict=False, reason="BUG-050: parser answer-key coverage is incomplete/corrupted")
def test_live_bank_answer_key_matches_independent_fixture(
    fixture_path: Path,
    book_ref: str,
    skill: str,
    test_number: str,
) -> None:
    fixture = _load(fixture_path)["tests"][test_number]["answers"]
    live_path = SERVICE_ROOT / "data" / "parsed" / book_ref / skill / f"test{test_number}.json"
    live = _load(live_path)["answer_key"]

    assert live == fixture

