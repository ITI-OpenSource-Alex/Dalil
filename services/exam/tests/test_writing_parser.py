from __future__ import annotations

from app.ingestion.writing_parser import WritingParser


def test_writing_parser_extracts_task1_and_task2() -> None:
    parser = WritingParser()

    parsed = parser.parse_text(_cambridge_writing_fixture())

    assert parsed["skill_area"] == "writing"
    assert parsed["book_ref"] == "IELTS-18"
    assert parsed["test_number"] == 1
    assert parsed["time_limit_seconds"] == 3600
    assert len(parsed["questions"]) == 2

    task1 = parsed["questions"][0]
    assert task1["number"] == 1
    assert task1["question_type"] == "Writing Task 1"
    assert (
        "graph" in task1["prompt"].lower()
        or "summarise" in task1["instructions"].lower()
    )

    task2 = parsed["questions"][1]
    assert task2["number"] == 2
    assert task2["question_type"] == "Writing Task 2"


def test_writing_parser_detects_letter_task1_type() -> None:
    parser = WritingParser()

    parsed = parser.parse_text(_cambridge_writing_letter_fixture())

    task1 = parsed["questions"][0]
    assert "letter" in task1["instructions"].lower()


def test_writing_parser_returns_empty_answer_key() -> None:
    parser = WritingParser()

    parsed = parser.parse_text(_cambridge_writing_fixture())

    assert parsed["answer_key"] == {}


def test_writing_parser_sets_correct_metadata() -> None:
    parser = WritingParser()

    parsed = parser.parse_text(_cambridge_writing_fixture())

    assert parsed["exam_type"] == "academic"
    assert parsed["passage_text"] is None


def _cambridge_writing_fixture() -> str:
    return """
CAMBRIDGE IELTS 18 ACADEMIC TEST 1

WRITING TASK 1

You should spend about 20 minutes on this task.

The graph below shows the average monthly temperatures in three cities
over a 12-month period.

Summarise the information by selecting and reporting the main features,
and make comparisons where relevant.

Write at least 150 words.

WRITING TASK 2

You should spend about 40 minutes on this task.

Write about the following topic:

Some people believe that it is best to accept a bad situation, such as
an unsatisfactory job or shortage of money. Others argue that it is
better to try and improve such situations.

Discuss both these views and give your own opinion.

Give reasons for your answer and include any relevant examples from your
own knowledge or experience.

Write at least 250 words.
"""


def _cambridge_writing_letter_fixture() -> str:
    return """
CAMBRIDGE IELTS 16 GENERAL TRAINING TEST 1

WRITING TASK 1

You should spend about 20 minutes on this task.

You recently bought a piece of equipment for your kitchen but it did not
work. You phoned the shop but no action was taken.

Write a letter to the shop manager. In your letter
- describe the problem with the equipment
- explain what happened when you phoned the shop
- say what you would like the manager to do

Write at least 150 words.

You do NOT need to write any addresses.

Begin your letter as follows:

Dear Sir or Madam,

WRITING TASK 2

You should spend about 40 minutes on this task.

Write about the following topic:

In some cultures, children are often told that they can achieve anything
if they try hard enough.

What are the advantages and disadvantages of giving children this message?

Give reasons for your answer and include any relevant examples from your
own knowledge or experience.

Write at least 250 words.
"""
