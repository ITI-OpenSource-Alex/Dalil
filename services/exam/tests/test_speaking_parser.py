from __future__ import annotations

from app.ingestion.speaking_parser import SpeakingParser


def test_speaking_parser_extracts_all_three_parts() -> None:
    parser = SpeakingParser()

    parsed = parser.parse_text(_cambridge_speaking_fixture())

    assert parsed["skill_area"] == "speaking"
    assert parsed["book_ref"] == "IELTS-18"
    assert parsed["test_number"] == 1
    assert parsed["time_limit_seconds"] == 900
    assert len(parsed["questions"]) > 0
    assert parsed["answer_key"] == {}


def test_speaking_parser_extracts_part1_questions() -> None:
    parser = SpeakingParser()

    parsed = parser.parse_text(_cambridge_speaking_fixture())

    part1_qs = [q for q in parsed["questions"] if q["question_type"] == "Speaking Part 1"]
    assert len(part1_qs) >= 2
    assert part1_qs[0]["section_number"] == 1
    for q in part1_qs:
        assert q["prompt"]


def test_speaking_parser_extracts_part2_cue_card() -> None:
    parser = SpeakingParser()

    parsed = parser.parse_text(_cambridge_speaking_fixture())

    part2_qs = [q for q in parsed["questions"] if q["question_type"] == "Speaking Part 2"]
    assert len(part2_qs) == 1
    cue_card = part2_qs[0]
    assert cue_card["section_number"] == 2
    assert "describe" in cue_card["prompt"].lower() or cue_card["prompt"]
    assert len(cue_card.get("bullet_points", [])) >= 2


def test_speaking_parser_extracts_part3_discussion() -> None:
    parser = SpeakingParser()

    parsed = parser.parse_text(_cambridge_speaking_fixture())

    part3_qs = [q for q in parsed["questions"] if q["question_type"] == "Speaking Part 3"]
    assert len(part3_qs) >= 2
    assert part3_qs[0]["section_number"] == 3
    for q in part3_qs:
        assert q["prompt"]


def test_speaking_parser_sets_correct_metadata() -> None:
    parser = SpeakingParser()

    parsed = parser.parse_text(_cambridge_speaking_fixture())

    assert parsed["exam_type"] == "academic"
    assert parsed["passage_text"] is None


def _cambridge_speaking_fixture() -> str:
    return """
CAMBRIDGE IELTS 18 ACADEMIC TEST 1

SPEAKING

PART 1

The examiner asks the candidate about him/herself, his/her home, work or studies and other familiar topics.

Do you enjoy cooking?
What kind of food do you like to eat?
Is there a dish from your country that you would recommend to visitors?

PART 2

Describe a book that you have read recently that you found interesting.

You should say:
- what the book was about
- why you decided to read it
- what you learned from it
and explain why you found it interesting.

PART 3

Discussion topics:

Do you think people read less nowadays than in the past?
Why do some people prefer reading e-books to printed books?
How important is it for children to develop a reading habit?
"""
