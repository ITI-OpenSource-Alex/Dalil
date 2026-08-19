from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import get_question_repository, router as internal_router
from app.ingestion.listening_parser import ListeningParser
from app.ingestion.reading_parser import ReadingParser
from app.services.question_ingestion_service import QuestionIngestionService


class FakeQuestionRepository:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def upsert_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = next(
            (
                record
                for record in self.records
                if (record["book_ref"], record["test_number"], record["skill_area"])
                == (
                    payload["book_ref"],
                    payload["test_number"],
                    payload["skill_area"],
                )
            ),
            None,
        )
        if existing is not None:
            return existing

        self.records.append(payload)
        return payload

    async def get_question_bank_stats(self) -> list[dict[str, Any]]:
        return [
            {
                "exam_type": record["exam_type"],
                "skill_area": record["skill_area"],
                "count": 1,
            }
            for record in self.records
        ]

    async def get_question_bank_stats_by_book(self) -> list[dict[str, Any]]:
        from collections import Counter

        counts: Counter[tuple[str, str, str]] = Counter()
        for record in self.records:
            key = (record["book_ref"], record["exam_type"], record["skill_area"])
            counts[key] += 1
        return [
            {
                "book_ref": book_ref,
                "exam_type": exam_type,
                "skill_area": skill_area,
                "count": count,
            }
            for (book_ref, exam_type, skill_area), count in sorted(counts.items())
        ]


def test_reading_parser_detects_three_passages_and_40_questions() -> None:
    parser = ReadingParser()

    parsed = parser.parse_text(_cambridge_reading_fixture())

    assert parsed["book_ref"] == "IELTS-18"
    assert parsed["test_number"] == 1
    assert parsed["exam_type"] == "academic"
    assert len(parsed["questions"]) == 40
    passages = parsed["passage_text"].split("\n\n---\n\n")
    assert len(passages) == 3


def test_reading_parser_preserves_numbering_and_classifies_question_types() -> None:
    parser = ReadingParser()

    parsed = parser.parse_text(_cambridge_reading_fixture())
    question_types = [question["question_type"] for question in parsed["questions"][:6]]
    numbering = [question["number"] for question in parsed["questions"][:6]]

    assert numbering == [1, 2, 3, 4, 5, 6]
    assert question_types == [
        "Multiple Choice",
        "Matching Headings",
        "True / False / Not Given",
        "Sentence Completion",
        "Short Answer",
        "Summary Completion",
    ]


def test_listening_parser_detects_four_sections_and_generates_s3_keys() -> None:
    parser = ListeningParser()

    parsed = parser.parse_text(_cambridge_listening_fixture())

    assert parsed["skill_area"] == "listening"
    assert len(parsed["questions"]) == 40
    assert parsed["audio_s3_key"] == "exam-audio/IELTS-18/1/section1.mp3"
    assert parsed["time_limit_seconds"] == 2400
    assert [question["number"] for question in parsed["questions"]] == list(
        range(1, 41)
    )
    assert {question["section_number"] for question in parsed["questions"]} == {
        1,
        2,
        3,
        4,
    }


def test_listening_parser_handles_cambridge_ranges_and_completion_gaps() -> None:
    parser = ListeningParser()
    source = """
CAMBRIDGE IELTS 19 ACADEMIC TEST 1
LISTENING
PART 1 Questions 1310
Complete the notes below.
Area: 1 ........ hectares
Habitats include a 2 ........
Children collect 3 ........ about plants.
Use a 4 ........ and compass.
The park's 5 ........
Children make 6 ........
They gain 7 ........
Children learn new 8 ........
Cost: 9 ........
Adults, such as 10 ........, free
PART 2 Questions 11320
Questions 11-15
Choose the correct letter, A, B or C.
11 What did members enjoy?
A option one
B option two
C option three
12 Question twelve?
13 Question thirteen?
14 Question fourteen?
15 Question fifteen?
Questions 16-20
Label the map below.
16 Farm shop
17 Disabled entry
18 Adventure playground
19 Kitchen gardens
20 Temple
PART 3 Questions 21330
Questions 21 and 22
Choose TWO answers from the box.
Options A-H
Questions 23 and 24
Choose TWO answers from the box.
Questions 25-30
Which comment applies to each item?
25 Item one
26 Item two
27 Item three
28 Item four
29 Item five
30 Item six
PART 4 Questions 31340
Complete the notes below.
31 first gap
32 second gap
33 third gap
34 fourth gap
35 fifth gap
36 sixth gap
37 seventh gap
38 eighth gap
39 ninth gap
40 tenth gap
READING
"""

    parsed = parser.parse_text(source)

    assert len(parsed["questions"]) == 40
    assert "Area:" in parsed["questions"][0]["prompt"]
    assert parsed["questions"][10]["prompt"].startswith("What did members enjoy?")
    assert parsed["questions"][15]["question_type"] == "Diagram Labelling"


@pytest.mark.parametrize(
    ("book", "test_number"),
    [
        ("IELTS15", 1),
        ("IELTS15", 2),
        ("IELTS15", 3),
        ("IELTS15", 4),
        ("IELTS19", 1),
    ],
)
def test_curated_listening_banks_are_complete_and_listening_only(
    book: str,
    test_number: int,
) -> None:
    data_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "parsed"
        / book
        / "listening"
        / f"test{test_number}.json"
    )
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    questions = payload["questions"]
    answers = payload["answer_key"]["answers"]
    prompt_text = " ".join(question["prompt"] for question in questions).lower()

    assert [question["number"] for question in questions] == list(range(1, 41))
    assert {question["section_number"] for question in questions} == {1, 2, 3, 4}
    assert all(question["prompt"].strip() for question in questions)
    assert set(answers) == {str(number) for number in range(1, 41)}
    assert payload["audio_s3_key"] == (
        f"exam-audio/IELTS-{book.removeprefix('IELTS')}/{test_number}/section1.mp3"
    )
    assert payload["time_limit_seconds"] == 2400
    assert "reading passage" not in prompt_text
    assert "listening and reading answer keys" not in prompt_text


@pytest.mark.parametrize("test_number", range(1, 5))
def test_curated_listening_multiple_choice_questions_have_structured_options(
    test_number: int,
) -> None:
    """Real UI controls need one option set per multiple-choice question.

    Flattening several questions and all of their choices into one OCR prompt
    leaves the browser able to show only a free-text fallback. The data contract
    must preserve choices independently of visual layout.
    """
    data_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "parsed"
        / "IELTS15"
        / "listening"
        / f"test{test_number}.json"
    )
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    multiple_choice = [
        question
        for question in payload["questions"]
        if "multiple choice" in question["question_type"].lower()
    ]

    assert multiple_choice, "fixture must exercise real multiple-choice content"
    assert all(
        isinstance(question.get("options"), list) and len(question["options"]) >= 2
        for question in multiple_choice
    ), "every multiple-choice question must carry its own structured options"


def test_answer_keys_are_parsed_from_cambridge_style_pages() -> None:
    parser = ReadingParser()

    parsed = parser.parse_text(_cambridge_reading_fixture())

    assert parsed["answer_key"]["1"] == "B"
    assert parsed["answer_key"]["40"] == "NOT GIVEN"


@pytest.mark.asyncio
async def test_ingesting_sample_reading_test_stores_40_questions() -> None:
    repository = FakeQuestionRepository()
    service = QuestionIngestionService(repository)

    record = await service.ingest(_cambridge_reading_fixture(), skill_area="reading")

    assert record["skill_area"] == "reading"
    assert len(record["questions"]) == 40


@pytest.mark.asyncio
async def test_ingestion_is_idempotent_for_same_book_test_and_skill() -> None:
    repository = FakeQuestionRepository()
    service = QuestionIngestionService(repository)

    first = await service.ingest(_cambridge_reading_fixture(), skill_area="reading")
    second = await service.ingest(_cambridge_reading_fixture(), skill_area="reading")

    assert first["book_ref"] == second["book_ref"]
    assert len(repository.records) == 1
    assert len(second["questions"]) == 40


def test_internal_stats_endpoint_returns_non_zero_counts() -> None:
    """A seeded bank reports what it holds.

    This previously built an EMPTY repository and still asserted
    `academic.reading >= 1`, which the endpoint satisfied by hardcoding a 1
    whenever the stats query came back empty. The test was the reason the lie
    existed -- it demanded a non-zero count from a bank containing nothing. Seed
    a record and the assertion holds for the right reason (BUG-020).
    """
    repo = FakeQuestionRepository()
    repo.records.append(
        {
            "book_ref": "IELTS-14",
            "test_number": 1,
            "exam_type": "academic",
            "skill_area": "reading",
            "questions": [],
            "answer_key": {},
        }
    )

    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_question_repository] = lambda: repo

    client = TestClient(app)
    response = client.get(
        "/internal/question-bank/stats",
        headers={"X-Internal-API-Key": "test-internal-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["academic"]["reading"] >= 1


def test_internal_stats_endpoint_reports_zero_for_an_empty_bank() -> None:
    """The regression that matters: an empty bank must not claim to hold tests.

    It reported `academic.reading: 1` against a `questions` table with 0 rows, so
    anyone checking whether the bank had been seeded got a confident yes while
    /exam/reading/start was answering "No reading tests available" (BUG-020).
    """
    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_question_repository] = lambda: FakeQuestionRepository()

    client = TestClient(app)
    response = client.get(
        "/internal/question-bank/stats",
        headers={"X-Internal-API-Key": "test-internal-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["academic"]["reading"] == 0
    assert payload["academic"]["listening"] == 0
    assert payload["general"]["reading"] == 0
    assert payload["by_book"] == {}


@pytest.mark.asyncio
async def test_writing_ingestion_stores_record() -> None:
    repository = FakeQuestionRepository()
    service = QuestionIngestionService(repository)

    record = await service.ingest(_cambridge_writing_fixture(), skill_area="writing")

    assert record["skill_area"] == "writing"
    assert len(record["questions"]) == 2


@pytest.mark.asyncio
async def test_speaking_ingestion_stores_record() -> None:
    repository = FakeQuestionRepository()
    service = QuestionIngestionService(repository)

    record = await service.ingest(_cambridge_speaking_fixture(), skill_area="speaking")

    assert record["skill_area"] == "speaking"
    assert len(record["questions"]) > 0


def test_gt_reading_parser_tags_passage_section_types() -> None:
    parser = ReadingParser()

    parsed = parser.parse_text(_cambridge_gt_reading_fixture())

    assert parsed["exam_type"] == "general"
    passage1_qs = [q for q in parsed["questions"] if q.get("passage_number") == 1]
    passage2_qs = [q for q in parsed["questions"] if q.get("passage_number") == 2]
    passage3_qs = [q for q in parsed["questions"] if q.get("passage_number") == 3]

    for q in passage1_qs:
        assert q.get("section_type") == "social", f"Q{q['number']} should be 'social'"
    for q in passage2_qs:
        assert q.get("section_type") == "work", f"Q{q['number']} should be 'work'"
    for q in passage3_qs:
        assert q.get("section_type") == "general_interest", (
            f"Q{q['number']} should be 'general_interest'"
        )


def test_stats_endpoint_includes_by_book_breakdown() -> None:
    repo = FakeQuestionRepository()
    repo.records.append(
        {
            "book_ref": "IELTS-14",
            "test_number": 1,
            "exam_type": "academic",
            "skill_area": "reading",
            "questions": [],
            "answer_key": {},
        }
    )
    repo.records.append(
        {
            "book_ref": "IELTS-14",
            "test_number": 1,
            "exam_type": "academic",
            "skill_area": "listening",
            "questions": [],
            "answer_key": {},
        }
    )
    repo.records.append(
        {
            "book_ref": "IELTS-15",
            "test_number": 1,
            "exam_type": "academic",
            "skill_area": "reading",
            "questions": [],
            "answer_key": {},
        }
    )

    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_question_repository] = lambda: repo

    client = TestClient(app)
    response = client.get(
        "/internal/question-bank/stats",
        headers={"X-Internal-API-Key": "test-internal-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "by_book" in payload
    assert "IELTS-14" in payload["by_book"]
    assert payload["by_book"]["IELTS-14"]["academic"]["reading"] == 1
    assert payload["by_book"]["IELTS-14"]["academic"]["listening"] == 1
    assert "IELTS-15" in payload["by_book"]
    assert payload["by_book"]["IELTS-15"]["academic"]["reading"] == 1


def _cambridge_reading_fixture() -> str:
    """Return synthetic Cambridge IELTS 18 text that exercises every parser strategy.

    Passage 1 (Q1-13): six different question types (MC, Matching Headings,
    TFNG, Sentence Completion, Short Answer, Summary Completion).
    Passage 2 (Q14-26): numbered multiple-choice questions.
    Passage 3 (Q27-40): numbered multiple-choice questions.

    The "WRITING" marker terminates the reading section so the answer-key
    lines are not inside any passage block.
    """
    return """
CAMBRIDGE IELTS 18 ACADEMIC TEST 1
READING PASSAGE 1
Urban green spaces have long been considered essential to the health and
wellbeing of city residents. Studies conducted across multiple European
capitals show that access to parks correlates with improved mental health
outcomes. Modern urban planners face increasing pressure to balance
commercial development with the preservation of community areas. The
research surveyed over two thousand households and found strong support
for expanded park access and pedestrian-friendly design.
Questions 1-1
Choose the correct letter, A, B or C.
1 The writer suggests that urban planners should
A protect public spaces
B reduce pedestrian areas
C limit park access
Questions 2-2
Choose the correct heading for each section of the passage.
2 Section A describes the survey methodology and participant demographics.
Questions 3-3
Do the following statements agree with the information given in the passage?
3 Urban planners have always prioritized green spaces in city design.
TRUE FALSE NOT GIVEN
Questions 4-4
Complete the sentences below.
4 The city parks were designed to provide__(shade)__.
Questions 5-5
Answer the questions below using no more than two words.
5 What did the survey respondents value most about their local environment?
Questions 6-13
Complete the summary below.
The study revealed that urban green spaces are essential for 6... health benefits. Researchers found that parks near 7... residential areas attracted more visitors. The report concluded that 8... strategic planning should incorporate 9... community feedback to improve 10... public outcomes. Additionally 11... local infrastructure plays a role in 12... sustainable development. The recommendation emphasized 13... ongoing engagement with residents.
READING PASSAGE 2
Bees are remarkable creatures whose communication methods have fascinated
scientists for decades. The waggle dance allows forager bees to convey the
direction and distance of food sources to their hive mates. Recent studies
have also examined how environmental factors such as temperature and light
affect bee navigation patterns. Colony health depends on the efficient
exchange of information among thousands of individual workers.
Questions 14-26
Choose the correct letter, A, B or C.
14 What aspect of bee communication is discussed first in the passage?
A dance patterns
B migration routes
C sleep cycles
15 The waggle dance primarily conveys information about
A hive temperature
B food location
C predator warnings
16 According to the passage environmental factors include
A temperature and light
B wind and rain
C soil and water
17 Colony health depends mainly on
A queen longevity
B information exchange
C honey production
18 The research methodology involved
A laboratory experiments
B field observations
C computer simulations
19 Scientists have studied bee communication for
A a few years
B several decades
C over a century
20 Forager bees communicate with
A individual scouts
B hive mates
C queen bees
21 The passage suggests that navigation patterns are affected by
A colony size
B environmental factors
C bee age
22 Recent studies have focused on
A bee genetics
B environmental effects on navigation
C honey composition
23 The direction of food sources is conveyed through
A chemical signals
B sound patterns
C the waggle dance
24 Worker bees number in
A hundreds
B thousands
C millions
25 The primary purpose of bee communication is
A defense
B reproduction
C foraging efficiency
26 The passage concludes that bees are
A endangered species
B remarkable creatures
C solitary insects
READING PASSAGE 3
Modern architecture has undergone significant transformations in the past
century. The shift from ornamental facades to minimalist glass structures
reflects broader changes in cultural values and technological capability.
Sustainable building practices have become a central concern as architects
seek to reduce the environmental impact of new construction. The use of
recycled materials and energy-efficient design principles now defines the
cutting edge of architectural innovation.
Questions 27-40
Choose the correct letter, A, B or C.
27 Modern architecture emphasizes
A functionality over ornament
B historical preservation
C rural development
28 The shift in architectural style reflects changes in
A building regulations
B cultural values
C population growth
29 Sustainable practices focus on reducing
A construction time
B labor costs
C environmental impact
30 Glass structures became popular because of
A lower material costs
B technological advances
C government mandates
31 Recycled materials are now used to
A cut costs only
B improve sustainability
C meet legal requirements
32 Energy-efficient design is considered
A optional for new buildings
B cutting edge innovation
C outdated practice
33 The passage covers architecture from
A the medieval period
B the past century
C ancient civilizations
34 Minimalist design replaced
A functional layouts
B ornamental facades
C wooden structures
35 Architects today seek to
A maximize floor space
B reduce environmental impact
C increase building height
36 The cutting edge of architecture involves
A traditional materials
B innovation in design
C larger buildings
37 Cultural values influence
A only interior design
B architectural style
C construction schedules
38 Technological capability enabled
A taller buildings only
B new structural forms
C cheaper construction
39 New construction aims to be
A faster and cheaper
B larger and taller
C sustainable and efficient
40 The overall tone of the passage is
A critical of modern trends
B neutral and informative
C nostalgic for past styles
WRITING
Answer key
1 B
2 B
3 TRUE
4 shade
5 environment
6 health
7 residential
8 strategic
9 community
10 public
11 local
12 sustainable
13 ongoing
14 A
15 B
16 A
17 B
18 B
19 B
20 B
21 B
22 B
23 C
24 B
25 C
26 B
27 A
28 B
29 C
30 B
31 B
32 B
33 B
34 B
35 B
36 B
37 B
38 B
39 C
40 NOT GIVEN
"""


def _cambridge_listening_fixture() -> str:
    return """
CAMBRIDGE IELTS 18 ACADEMIC TEST 1
LISTENING SECTION 1
Questions 1-10
1. Listen and complete the form.
2. Listen and write one word and a number.
3. Listen and complete the form.
4. Listen and complete the form.
5. Listen and complete the form.
6. Listen and complete the form.
7. Listen and complete the form.
8. Listen and complete the form.
9. Listen and complete the form.
10. Listen and complete the form.
SECTION 2
Questions 11-20
11. Choose the correct letter.
12. Choose the correct letter.
13. Choose the correct letter.
14. Choose the correct letter.
15. Choose the correct letter.
16. Choose the correct letter.
17. Choose the correct letter.
18. Choose the correct letter.
19. Choose the correct letter.
20. Choose the correct letter.
SECTION 3
Questions 21-30
21. Listen and complete the notes.
22. Listen and complete the notes.
23. Listen and complete the notes.
24. Listen and complete the notes.
25. Listen and complete the notes.
26. Listen and complete the notes.
27. Listen and complete the notes.
28. Listen and complete the notes.
29. Listen and complete the notes.
30. Listen and complete the notes.
SECTION 4
Questions 31-40
31. Listen and complete the summary.
32. Listen and complete the summary.
33. Listen and complete the summary.
34. Listen and complete the summary.
35. Listen and complete the summary.
36. Listen and complete the summary.
37. Listen and complete the summary.
38. Listen and complete the summary.
39. Listen and complete the summary.
40. Listen and complete the summary.
"""


def _cambridge_gt_reading_fixture() -> str:
    """Synthetic General Training reading test with 3 passages and 40 questions."""
    return """
CAMBRIDGE IELTS 18 GENERAL TRAINING TEST 1
READING
READING PASSAGE 1
Welcome to Greenfield Community Centre. Opening hours: Monday to Friday
9am-5pm, Saturday 10am-2pm. Membership fees: Adults $50/year, Students
$25/year, Seniors $30/year. All new members must register at reception
and bring photo identification. Swimming pool access requires a separate
booking. Children under 12 must be accompanied by an adult at all times.
Questions 1-13
Choose the correct letter, A, B or C.
1 The community centre is open on Saturdays from
A 9am to 5pm
B 10am to 2pm
C 10am to 5pm
2 Student membership costs
A $25 per year
B $30 per year
C $50 per year
3 New members must bring
A a reference letter
B photo identification
C proof of address
4 Swimming pool access requires
A a membership card
B a separate booking
C an instructor
5 Children under 12 must be
A registered separately
B accompanied by an adult
C enrolled in a program
6 Adult membership costs
A $25 per year
B $30 per year
C $50 per year
7 The centre closes on weekdays at
A 2pm
B 4pm
C 5pm
8 Senior membership costs
A $25 per year
B $30 per year
C $50 per year
9 Registration takes place at
A the pool
B reception
C online
10 The centre is closed on
A Sundays
B Mondays
C Saturdays
11 Pool access is
A free for members
B included in membership
C booked separately
12 Photo ID is required for
A pool access
B new registration
C all visits
13 The passage is about
A a gym
B a community centre
C a school
READING PASSAGE 2
Workplace Safety Guidelines for Factory Floor Staff. All employees must
wear protective equipment including hard hats, safety goggles, and
steel-toed boots while on the factory floor. Emergency exits are marked
with green signs and must not be blocked at any time. Fire drills are
conducted monthly. Report any hazards to your supervisor immediately.
First aid kits are located at each workstation. Visitors must check in
at the security desk and be escorted at all times.
Questions 14-26
Choose the correct letter, A, B or C.
14 Employees must wear
A casual clothing
B protective equipment
C uniforms
15 Emergency exits are marked with
A red signs
B blue signs
C green signs
16 Fire drills happen
A weekly
B monthly
C annually
17 Hazards should be reported to
A HR department
B the supervisor
C security
18 First aid kits are at
A the entrance
B each workstation
C the cafeteria
19 Visitors must
A wear hard hats
B check in at security
C park in designated areas
20 Safety goggles are
A optional
B required on factory floor
C only for supervisors
21 Emergency exits must not be
A locked
B blocked
C painted
22 Steel-toed boots are required
A in offices
B on factory floor
C in parking areas
23 Visitors must be
A photographed
B escorted
C trained
24 Hard hats are part of
A visitor equipment
B protective equipment
C office supplies
25 The guidelines are for
A office workers
B factory floor staff
C management
26 First aid is available at
A the hospital
B the office
C each workstation
READING PASSAGE 3
The development of renewable energy sources has transformed the global
energy landscape over the past two decades. Solar panel efficiency has
improved dramatically while costs have decreased by over eighty percent
since 2010. Wind farms now generate a significant portion of electricity
in many European countries. However challenges remain in energy storage
technology which is essential for managing the intermittent nature of
renewable sources. Battery technology advances particularly in lithium
ion and solid state designs offer promising solutions for grid-scale
energy storage.
Questions 27-40
Choose the correct letter, A, B or C.
27 Solar panel costs have
A increased steadily
B decreased significantly
C remained stable
28 Wind farms are significant in
A Asian countries
B European countries
C African countries
29 The main challenge is
A solar efficiency
B energy storage
C wind speed
30 Battery technology includes
A hydrogen cells
B lithium ion designs
C nuclear fusion
31 Renewable energy development spans
A five years
B one decade
C two decades
32 Solar efficiency has
A declined
B improved dramatically
C stayed the same
33 Energy storage is essential for
A reducing costs
B managing intermittency
C increasing production
34 Solid state designs are
A outdated
B promising
C expensive
35 The passage discusses
A fossil fuels
B renewable energy
C nuclear power
36 Grid-scale storage requires
A government funding
B advanced batteries
C new regulations
37 Cost reduction since 2010 exceeds
A fifty percent
B seventy percent
C eighty percent
38 Wind energy generates
A all electricity
B minimal electricity
C significant electricity
39 Renewable sources are
A constant
B intermittent
C predictable
40 The overall outlook for renewables is
A pessimistic
B uncertain
C promising
WRITING
Answer key
1 B
2 A
3 B
4 B
5 B
6 C
7 C
8 B
9 B
10 A
11 C
12 B
13 B
14 B
15 C
16 B
17 B
18 B
19 B
20 B
21 B
22 B
23 B
24 B
25 B
26 C
27 B
28 B
29 B
30 B
31 C
32 B
33 B
34 B
35 B
36 B
37 C
38 C
39 B
40 C
"""


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


def _cambridge_speaking_fixture() -> str:
    return """
CAMBRIDGE IELTS 18 ACADEMIC TEST 1

SPEAKING

PART 1

The examiner asks the candidate about him/herself.

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


def test_reading_parser_stops_at_answer_key_when_writing_marker_missing() -> None:
    parser = ReadingParser()
    test_block = """Test 3
READING
READING PASSAGE 1
This is passage 1.
Questions 1-3
1 A
2 B
3 C
Answer key
Reading Passage 1, Questions 1-3
1 A
"""
    reading_section = parser._isolate_reading_section(test_block)
    assert "Answer key" not in reading_section
    assert "This is passage 1." in reading_section
