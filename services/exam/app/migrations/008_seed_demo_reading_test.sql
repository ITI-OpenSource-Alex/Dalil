-- Seed one complete, gradable Reading test for demo purposes.
--
-- Demo-readiness plan doc 01 (docs/dorgham-context/implementation-plan/
-- demo-readiness-plan/01-reading-exam-data.md): the questions table had zero
-- rows for skill_area='reading' -- 005_seed_writing_questions.sql was left
-- empty, and the only other way rows get in is the OCR ingestion pipeline,
-- which has no CLI/HTTP entry point in normal operation. Without at least one
-- row, POST /sessions (create_session, called by the frontend's "Take Exam")
-- returns 404 and the Reading exam -- the strongest asset in the demo --
-- cannot be started at all.
--
-- Route A (running the ingestion pipeline against a former repo-root export)
-- was attempted first per the implementation plan and abandoned immediately:
-- that file was a Trello board
-- export (top-level keys: id, name, desc, cards, checklists, customFields,
-- labels, lists, members, actions), not Cambridge OCR text, and is not a
-- valid input to ReadingParser.parse_text under any reading of its shape.
-- This migration is Route B, the documented fallback: a single
-- hand-authored test.
--
-- Content notes:
--  - 15 questions (not the full 40) spanning all 5 Cambridge question-type
--    renderers the frontend implements (Multiple Choice, Matching,
--    True/False/Not Given, Sentence Completion -> fill_in_blank, Short
--    Answer), 3 per type.
--  - Question numbers (1-5, 14-18, 27-31) are chosen deliberately to land
--    one cluster inside each of the three fixed section ranges the backend
--    and frontend both hardcode independently (READING_SECTION_RANGES in
--    services/exam/app/services/grading_service.py and
--    services/frontend/lib/reading-sections.ts): section_1 = 1-13,
--    section_2 = 14-26, section_3 = 27-40. This is what makes Section 1/2/3
--    tabs and the per-section results breakdown show real, non-empty data
--    for all three sections instead of only one.
--  - passage_text joins 3 passages with "---", split identically by
--    ReadingParser (\n\n---\n\n) and the frontend's splitPassages()
--    (splits on "---", trims). Passage 1 pairs with section 1 (Q1-5),
--    passage 2 with section 2 (Q14-18), passage 3 with section 3 (Q27-31) --
--    the exam shell renders passages[activeSection - 1], so this ordering
--    is load-bearing, not cosmetic.
--  - Multiple Choice / Matching options are embedded as "A. ...", "B. ..."
--    lines inside each question's prompt text, matching the frontend's
--    OPTION_LINE regex in normalizeReadingQuestions.ts (there is no
--    structured options field on the backend). The stored answer is the
--    option letter, matching what the UI's radio/select control submits.
--  - answer_key is a FLAT object with exactly one key per question number,
--    matching questions_repository.py's _SCORABLE_CLAUSE
--    (count(jsonb_object_keys(answer_key)) = jsonb_array_length(questions)),
--    which excludes any test from being served at all if the two counts
--    disagree.
--
-- Known operational limitation (see the runbook): get_random_question's
-- LEFT JOIN excludes any question a given user_id already has *any* session
-- against, seen or not. With only this one test seeded, a second Reading
-- exam attempt from the same account will find nothing -- always use a
-- fresh account per Reading-exam demo run.

INSERT INTO questions (
    book_ref,
    test_number,
    exam_type,
    skill_area,
    passage_text,
    audio_s3_key,
    questions,
    answer_key
)
VALUES (
    'GOA-DEMO',
    1,
    'academic',
    'reading',
    $passage$Over the last two decades, keeping honeybees has quietly become one of the most popular hobbies in major cities around the world. Rooftops in New York, balconies in Paris and community gardens in London now host thousands of hives that would once have been found only in rural orchards. Advocates argue that urban beekeeping helps reverse the decline of pollinator populations, which have fallen sharply due to pesticide use, habitat loss and disease. Cities, they point out, can actually offer bees a surprising advantage: a longer flowering season, thanks to the mix of ornamental gardens, street trees and window boxes that bloom at different times throughout the year, and far less exposure to the agricultural pesticides used on large monoculture farms.

Not every expert agrees that filling cities with hives is an unqualified good, however. Some ecologists caution that a sudden rise in managed honeybee colonies can crowd out wild, native pollinator species, such as solitary bees and bumblebees, that are already struggling to find food. Because a single hive can contain up to sixty thousand bees, a handful of rooftop apiaries in one neighbourhood can consume a large share of the available nectar, leaving little for wild insects that cannot travel as far to forage. A 2019 study of Central London found measurable competition between managed honeybees and wild bee species within a two-kilometre radius of dense hive clusters.

City authorities have responded in different ways. Some, including several London boroughs, now cap the number of hives permitted per site and encourage residents to plant native wildflowers instead. Others actively promote beekeeping as an educational tool, arguing that direct contact with hives teaches city dwellers to value insects they would otherwise ignore or fear. What most researchers agree on is that urban beekeeping alone cannot solve the pollinator crisis; it must be paired with planting policies that support a wider range of species, not just the honeybee.

---

Coral reefs cover less than one per cent of the ocean floor, yet they support around a quarter of all known marine species, making them one of the richest ecosystems on the planet. Built over thousands of years by tiny animals called polyps, reefs provide food, shelter and breeding grounds for fish, crustaceans and countless other organisms, while also protecting coastlines from storms and erosion. For the hundreds of millions of people who depend on reef fisheries and tourism for their livelihoods, healthy coral is not a luxury but an economic necessity.

In recent decades, however, rising sea temperatures have placed enormous strain on reef systems worldwide. When water becomes too warm, corals expel the colourful algae living in their tissues in a process known as bleaching, leaving behind a stark white skeleton. A bleached coral is not immediately dead, but it is under severe stress and will die within weeks if warm conditions persist. Major bleaching events have struck the Great Barrier Reef repeatedly since 2016, and scientists now warn that if global temperatures rise by more than two degrees Celsius, most tropical reefs could disappear entirely within this century.

Conservationists are testing a range of responses. Some laboratories are breeding coral strains that tolerate higher temperatures, then transplanting them onto damaged reefs in the hope that resilience will spread naturally over time. Others are focused on reducing local stressors, such as pollution and overfishing, on the theory that a reef under less pressure from multiple directions stands a better chance of recovering from heat stress. A smaller number of projects have experimented with artificial shading structures suspended above vulnerable reef sections, though the cost of scaling this approach to entire reef systems remains prohibitive. Most scientists agree that local interventions can buy time, but that only a serious reduction in global carbon emissions will determine whether reefs survive in the long term.

---

For much of the late twentieth century, the overnight train seemed destined for extinction. Budget airlines offered fares that undercut sleeper services on almost every European route, and high-speed daytime trains cut journey times so dramatically that spending eight hours asleep on a train felt like an inefficient use of time. By the early 2010s, national operators in France, Germany and elsewhere had quietly withdrawn dozens of overnight routes, and many observers assumed the sleeper carriage would soon be a historical curiosity, preserved only for tourists nostalgic for a slower era of travel.

That assumption has proven wrong. Since around 2020, overnight rail services have expanded again across the continent, with new or restored routes connecting cities such as Vienna, Amsterdam, Berlin and Stockholm. Several factors have driven the revival. Growing public concern about the carbon emissions produced by short-haul flights has pushed travellers, particularly younger ones, to seek lower-carbon alternatives for journeys of a few hundred kilometres. At the same time, several governments have introduced taxes on domestic flights or subsidies for rail operators, narrowing the price gap that once made trains the more expensive option. Austria's state railway became an unlikely leader in this revival, acquiring sleeper carriages from other national operators as they exited the market and building a network that by 2023 served more than twenty European cities.

Challenges remain. Sleeper trains are expensive to operate relative to the number of passengers they carry, since a compartment that might seat six people during the day typically sleeps only two or three at night. Rolling stock is also ageing, and building new sleeper carriages requires specialised manufacturing capacity that all but disappeared during the industry's decline. Even so, bookings on many revived routes have consistently outstripped capacity, suggesting that demand, at least, is no longer the obstacle it once was.$passage$,
    NULL,
    $questions$[
      {
        "number": 1,
        "question_type": "Multiple Choice",
        "instructions": "Choose the correct letter, A, B, C or D.",
        "passage_number": 1,
        "section_number": 1,
        "prompt": "According to the passage, what advantage do cities sometimes offer honeybees compared with rural farmland?\nA. Warmer temperatures throughout the year\nB. A longer flowering season with more varied plants\nC. Fewer natural predators such as birds\nD. Larger areas of open land for foraging"
      },
      {
        "number": 2,
        "question_type": "Multiple Choice",
        "instructions": "Choose the correct letter, A, B, C or D.",
        "passage_number": 1,
        "section_number": 1,
        "prompt": "What concern do some ecologists raise about rising numbers of managed honeybee hives in cities?\nA. Honeybees produce less honey in urban environments\nB. Hives are more likely to be damaged by weather\nC. Honeybees may compete with wild pollinators for food\nD. City authorities cannot monitor hive numbers accurately"
      },
      {
        "number": 3,
        "question_type": "True/False/Not Given",
        "instructions": "Do the following statements agree with the information given in the passage? Write TRUE, FALSE, or NOT GIVEN.",
        "passage_number": 1,
        "section_number": 1,
        "prompt": "A single beehive can contain up to sixty thousand bees."
      },
      {
        "number": 4,
        "question_type": "True/False/Not Given",
        "instructions": "Do the following statements agree with the information given in the passage? Write TRUE, FALSE, or NOT GIVEN.",
        "passage_number": 1,
        "section_number": 1,
        "prompt": "All city authorities have banned rooftop beekeeping."
      },
      {
        "number": 5,
        "question_type": "Short Answer",
        "instructions": "Answer the question below. Write NO MORE THAN THREE WORDS.",
        "passage_number": 1,
        "section_number": 1,
        "prompt": "In which city did a 2019 study find competition between managed and wild bees?"
      },
      {
        "number": 14,
        "question_type": "Sentence Completion",
        "instructions": "Complete the sentence below. Write NO MORE THAN TWO WORDS.",
        "passage_number": 2,
        "section_number": 2,
        "prompt": "Coral reefs cover less than ______ per cent of the ocean floor."
      },
      {
        "number": 15,
        "question_type": "Sentence Completion",
        "instructions": "Complete the sentence below. Write NO MORE THAN TWO WORDS.",
        "passage_number": 2,
        "section_number": 2,
        "prompt": "When water becomes too warm, corals expel the algae living in their tissues in a process called ______."
      },
      {
        "number": 16,
        "question_type": "Matching Information",
        "instructions": "Choose the correct answer, A, B, C or D.",
        "passage_number": 2,
        "section_number": 2,
        "prompt": "Which conservation approach is described as too costly to apply across entire reef systems?\nA. Breeding heat-tolerant coral strains\nB. Reducing local pollution and overfishing\nC. Artificial shading structures\nD. Relocating fish populations"
      },
      {
        "number": 17,
        "question_type": "Matching Information",
        "instructions": "Choose the correct answer, A, B, C or D.",
        "passage_number": 2,
        "section_number": 2,
        "prompt": "Which conservation approach relies on the idea that reducing stress from multiple directions helps a reef recover?\nA. Breeding heat-tolerant coral strains\nB. Reducing local pollution and overfishing\nC. Artificial shading structures\nD. Increasing tourism revenue"
      },
      {
        "number": 18,
        "question_type": "True/False/Not Given",
        "instructions": "Do the following statements agree with the information given in the passage? Write TRUE, FALSE, or NOT GIVEN.",
        "passage_number": 2,
        "section_number": 2,
        "prompt": "A bleached coral dies immediately."
      },
      {
        "number": 27,
        "question_type": "Short Answer",
        "instructions": "Answer the question below. Write NO MORE THAN THREE WORDS.",
        "passage_number": 3,
        "section_number": 3,
        "prompt": "Which country's state railway became a leader in the sleeper-train revival?"
      },
      {
        "number": 28,
        "question_type": "Short Answer",
        "instructions": "Answer the question below. Write NO MORE THAN THREE WORDS.",
        "passage_number": 3,
        "section_number": 3,
        "prompt": "By what year had this operator's network grown to serve more than twenty European cities?"
      },
      {
        "number": 29,
        "question_type": "Multiple Choice",
        "instructions": "Choose the correct letter, A, B, C or D.",
        "passage_number": 3,
        "section_number": 3,
        "prompt": "According to the passage, why did overnight trains decline in the late twentieth century?\nA. Passengers preferred slower journeys\nB. Budget airlines and high-speed trains made them less competitive\nC. Governments banned sleeper carriages\nD. Manufacturing of sleeper carriages was outlawed"
      },
      {
        "number": 30,
        "question_type": "Sentence Completion",
        "instructions": "Complete the sentence below. Write NO MORE THAN TWO WORDS.",
        "passage_number": 3,
        "section_number": 3,
        "prompt": "A sleeper compartment that might seat six people during the day typically sleeps only ______ or three at night."
      },
      {
        "number": 31,
        "question_type": "Matching Information",
        "instructions": "Choose the correct answer, A, B, C or D.",
        "passage_number": 3,
        "section_number": 3,
        "prompt": "Which factor is described as narrowing the price gap between flights and overnight trains?\nA. Falling airline fuel costs\nB. Taxes on domestic flights and rail subsidies\nC. Reduced train ticket demand\nD. New airport routes"
      }
    ]$questions$::jsonb,
    $answers${
      "1": "B",
      "2": "C",
      "3": "TRUE",
      "4": "FALSE",
      "5": "London",
      "14": "one",
      "15": "bleaching",
      "16": "C",
      "17": "B",
      "18": "FALSE",
      "27": "Austria",
      "28": "2023",
      "29": "B",
      "30": "two",
      "31": "B"
    }$answers$::jsonb
)
ON CONFLICT DO NOTHING;
