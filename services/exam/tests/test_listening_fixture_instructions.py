import json
from pathlib import Path


LISTENING_FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "parsed"
    / "IELTS15"
    / "listening"
)


def _questions(test_number: int) -> list[dict[str, object]]:
    path = LISTENING_FIXTURES / f"test{test_number}.json"
    return json.loads(path.read_text(encoding="utf-8"))["questions"]


def test_every_listening_question_has_group_instructions() -> None:
    for test_number in range(1, 5):
        missing = [
            question["number"]
            for question in _questions(test_number)
            if not str(question.get("instructions") or "").strip()
        ]

        assert missing == [], f"IELTS15 Listening Test {test_number}: {missing}"


def test_completion_groups_state_the_answer_length_limit() -> None:
    completion_types = {"Form Completion", "Notes Completion", "Table Completion"}

    for test_number in range(1, 5):
        invalid = [
            question["number"]
            for question in _questions(test_number)
            if question["question_type"] in completion_types
            and "WORD" not in str(question["instructions"])
        ]

        assert invalid == [], f"IELTS15 Listening Test {test_number}: {invalid}"


def test_test_three_first_group_preserves_the_number_allowance() -> None:
    first_group = _questions(3)[:10]

    assert {
        question["instructions"] for question in first_group
    } == {
        "Complete the notes below. Write ONE WORD AND/OR A NUMBER for each answer."
    }
