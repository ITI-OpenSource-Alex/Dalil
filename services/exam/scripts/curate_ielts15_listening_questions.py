"""Repair IELTS 15 Listening question semantics lost by flat OCR parsing.

The source text in data/ocr/IELTS15/full.txt contains the option groups, but
page-layout loss caused the generic parser to repeat whole blocks for each
question and to classify later completion sections as multiple choice.  Keep
this deterministic curation step beside the ingestion tooling so regenerated
fixtures can be repaired without hand-editing generated JSON.
"""

from __future__ import annotations

import json
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = SERVICE_ROOT / "data" / "parsed" / "IELTS15" / "listening"


def choices(stem: str, options: list[str]) -> dict[str, object]:
    return {"prompt": stem, "question_type": "Multiple Choice", "options": options}


def matching(stem: str, options: list[str]) -> dict[str, object]:
    return {"prompt": stem, "question_type": "Matching", "options": options}


def completion(stem: str, question_type: str = "Notes Completion") -> dict[str, object]:
    return {"prompt": stem, "question_type": question_type}


def map_label(stem: str, markers: str = "ABCDEFGHI") -> dict[str, object]:
    return {
        "prompt": stem,
        "question_type": "Map Labelling",
        "options": list(markers),
    }


CURATED: dict[int, dict[int, dict[str, object]]] = {
    1: {
        1: completion("Name of agent: Becky ___"),
        2: completion("Best to call her in the ___"),
        3: completion("Clerical and administrative applicants must have good ___"),
        4: completion("Jobs are usually for at least one ___"),
        5: completion("Pay is usually £___ per hour"),
        6: completion("Wear a ___ to the interview"),
        7: completion("Bring your ___ to the interview"),
        8: completion("The agency will ask questions about each applicant's ___"),
        9: completion("The ___ received at interview will benefit applicants"),
        10: completion("Less ___ is involved in applying for jobs through the agency"),
        11: choices(
            "According to the speaker, the company",
            [
                "has been in business for longer than most of its competitors.",
                "arranges holidays to more destinations than its competitors.",
                "has more customers than its competitors.",
            ],
        ),
        12: choices(
            "Where can customers meet the tour manager before travelling to the Isle of Man?",
            ["Liverpool", "Heysham", "Luton"],
        ),
        13: choices(
            "How many lunches are included in the price of the holiday?",
            ["three", "four", "five"],
        ),
        14: choices(
            "Customers have to pay extra for",
            [
                "guaranteeing themselves a larger room.",
                "booking at short notice.",
                "transferring to another date.",
            ],
        ),
        15: completion(
            "The hotel dining room has a view of the ___", "Table Completion"
        ),
        16: completion(
            "The earliest surviving reference to Tynwald is from ___",
            "Table Completion",
        ),
        17: completion(
            "The Snaefell Mountain Railway takes visitors to the ___ of Snaefell",
            "Table Completion",
        ),
        18: completion(
            "On the free day, a ___ covers local transport and heritage sites",
            "Table Completion",
        ),
        19: completion(
            "On Day 5, visitors travel on the ___ railway", "Table Completion"
        ),
        20: completion("Castletown is the island's former ___", "Table Completion"),
        **{
            number: matching(
                stem,
                [
                    "outgoing",
                    "selfish",
                    "independent",
                    "attention-seeking",
                    "introverted",
                    "co-operative",
                    "caring",
                    "competitive",
                ],
            )
            for number, stem in {
                21: "the eldest child",
                22: "a middle child",
                23: "the youngest child",
                24: "a twin",
                25: "an only child",
                26: "a child with much older siblings",
            }.items()
        },
        27: choices(
            "What do the speakers say about the evidence relating to birth order and academic success?",
            [
                "There is conflicting evidence about whether oldest children perform best in intelligence tests.",
                "There is little doubt that birth order has less influence on academic achievement than socio-economic status.",
                "Some studies have neglected to include important factors such as family size.",
            ],
        ),
        28: choices(
            "What does Ruth think is surprising about the difference in oldest children's academic performance?",
            [
                "It is mainly thanks to their roles as teachers for their younger siblings.",
                "The advantages they have only lead to a slightly higher level of achievement.",
                "The extra parental attention they receive at a young age makes little difference.",
            ],
        ),
        29: choices(
            "Which TWO experiences of sibling rivalry do the speakers agree have been valuable for them?",
            [
                "learning to share",
                "learning to stand up for oneself",
                "learning to be a good loser",
                "learning to be tolerant",
                "learning to say sorry",
            ],
        ),
        30: choices(
            "Which TWO experiences of sibling rivalry do the speakers agree have been valuable for them?",
            [
                "learning to share",
                "learning to stand up for oneself",
                "learning to be a good loser",
                "learning to be tolerant",
                "learning to say sorry",
            ],
        ),
        31: completion(
            "The eucalyptus provides ___ and food for a wide range of species"
        ),
        32: completion("Its leaves provide ___ which is used to make a disinfectant"),
        33: completion(
            "Lime used for making ___ was absorbed, preventing trees from taking in iron"
        ),
        34: completion("___ feed on eucalyptus leaves and secrete a sugary substance"),
        35: completion("High-frequency bushfires result in the growth of ___"),
        36: completion(
            "Mid-frequency bushfires make more ___ available to eucalyptus trees"
        ),
        37: completion("Mid-frequency bushfires maintain the quality of the ___"),
        38: completion(
            "Low-frequency bushfires result in the growth of ___ rainforest"
        ),
        39: completion("This rainforest is a ___ ecosystem"),
        40: completion("This rainforest is an ideal environment for the ___"),
    },
    2: {
        1: completion("18th: ballet company called ___"),
        2: completion("18th–20th: the comedy Jemima has had a good ___"),
        3: completion("20th evening: type of performance — ___"),
        4: completion("20th evening: name of show — ___"),
        5: completion("Cookery workshop: making food part of a ___ lifestyle"),
        6: completion("Children's workshop: making ___ about the town's history"),
        7: completion("Adults' workshop: making toys from ___ using various tools"),
        8: completion("Outdoor activity: swimming in the ___"),
        9: completion("Woodland walks are led by an expert on ___"),
        10: completion("See the festival organiser's ___ for more information"),
        11: choices(
            "The park was originally established",
            [
                "as an amenity provided by the city council.",
                "as land belonging to a private house.",
                "as a shared area set up by the local community.",
            ],
        ),
        12: choices(
            "Why is there a statue of Diane Gosforth in the park?",
            [
                "She was a resident who helped to lead a campaign.",
                "She was a council member responsible for giving the public access.",
                "She was a senior worker at the park for many years.",
            ],
        ),
        13: choices(
            "During the First World War, the park was mainly used for",
            ["exercises by troops.", "growing vegetables.", "public meetings."],
        ),
        14: choices(
            "When did the physical transformation of the park begin?",
            ["2013", "2015", "2016"],
        ),
        15: map_label("statue of Diane Gosforth"),
        16: map_label("wooden sculptures"),
        17: map_label("playground"),
        18: map_label("maze"),
        19: map_label("tennis courts"),
        20: map_label("fitness area"),
        21: choices(
            "Which TWO groups of people is the display primarily intended for?",
            [
                "students from the English department",
                "residents of the local area",
                "the university's teaching staff",
                "potential new students",
                "students from other departments",
            ],
        ),
        22: choices(
            "Which TWO groups of people is the display primarily intended for?",
            [
                "students from the English department",
                "residents of the local area",
                "the university's teaching staff",
                "potential new students",
                "students from other departments",
            ],
        ),
        23: choices(
            "What are Cathy and Graham's TWO reasons for choosing the novelist Charles Dickens?",
            [
                "His speeches inspired others to try to improve society.",
                "He used his publications to draw attention to social problems.",
                "His novels are well-known now.",
                "He was consulted on a number of social issues.",
                "His reputation has changed in recent times.",
            ],
        ),
        24: choices(
            "What are Cathy and Graham's TWO reasons for choosing the novelist Charles Dickens?",
            [
                "His speeches inspired others to try to improve society.",
                "He used his publications to draw attention to social problems.",
                "His novels are well-known now.",
                "He was consulted on a number of social issues.",
                "His reputation has changed in recent times.",
            ],
        ),
        **{
            number: matching(
                stem,
                [
                    "poverty",
                    "education",
                    "Dickens's travels",
                    "entertainment",
                    "wealth",
                    "medicine",
                    "a woman's life",
                    "crime and the law",
                ],
            )
            for number, stem in {
                25: "The Pickwick Papers",
                26: "Oliver Twist",
                27: "Nicholas Nickleby",
                28: "Martin Chuzzlewit",
                29: "Bleak House",
                30: "Little Dorrit",
            }.items()
        },
        31: completion("___ was the main priority to ensure the supply of water"),
        32: completion("Most work organised by farmers' associations was done by ___"),
        33: completion("The programme provided ___ for the fences"),
        34: completion("The programme provided ___ for suitable crops"),
        35: completion(
            "Local people provided and put up the ___ that supported the fences"
        ),
        36: completion(
            "Farmers had difficulty marketing produce because they lacked ___"
        ),
        37: completion("Training was provided in methods of food ___"),
        38: completion("Farmers made special places where ___ could be kept"),
        39: completion("Local people later suggested keeping ___"),
        40: completion("Enough time must be allowed, particularly for the ___ phase"),
    },
    3: {
        1: completion(
            "Administrative assistant in a company that produces ___ (North London)"
        ),
        2: completion("Responsibilities include organising ___ and taking notes"),
        3: completion("General administration includes management of a ___"),
        4: completion("Applicants must show attention to ___"),
        5: completion(
            "Applicants need a minimum of ___ of teleconferencing experience"
        ),
        6: completion("Warehouse responsibilities include managing ___"),
        7: completion("Applicants must be very organised and ___"),
        8: completion("Applicants must be used to working in a ___"),
        9: completion("Applicants must be able to cope with items that are ___"),
        10: completion("Applicants need experience of ___ service"),
        11: choices(
            "When did the Street Play Scheme first take place?",
            ["two years ago", "three years ago", "six years ago"],
        ),
        12: choices(
            "How often is Beechwood Road closed to traffic now?",
            ["once a week", "on Saturdays and Sundays", "once a month"],
        ),
        13: choices(
            "Who is responsible for closing the road?",
            ["a council official", "the police", "street wardens"],
        ),
        14: choices(
            "Residents who want to use their cars",
            [
                "have to park in another street.",
                "must drive very slowly.",
                "need permission from a warden.",
            ],
        ),
        15: choices(
            "Alice says that Street Play Schemes are most needed in",
            ["wealthy areas.", "quiet suburban areas.", "areas with heavy traffic."],
        ),
        16: choices(
            "What has been the reaction of residents who are not parents?",
            [
                "Many of them were unhappy at first.",
                "They like seeing children play in the street.",
                "They are surprised by the lack of noise.",
            ],
        ),
        17: choices(
            "Which TWO benefits for children does Alice think are the most important?",
            [
                "increased physical activity",
                "increased sense of independence",
                "opportunity to learn new games",
                "opportunity to be part of a community",
                "opportunity to make new friends",
            ],
        ),
        18: choices(
            "Which TWO benefits for children does Alice think are the most important?",
            [
                "increased physical activity",
                "increased sense of independence",
                "opportunity to learn new games",
                "opportunity to be part of a community",
                "opportunity to make new friends",
            ],
        ),
        19: choices(
            "Which TWO results of the King Street experiment surprised Alice?",
            [
                "more shoppers",
                "improved safety",
                "less air pollution",
                "more relaxed atmosphere",
                "less noise pollution",
            ],
        ),
        20: choices(
            "Which TWO results of the King Street experiment surprised Alice?",
            [
                "more shoppers",
                "improved safety",
                "less air pollution",
                "more relaxed atmosphere",
                "less noise pollution",
            ],
        ),
        21: completion("What ___ the newspaper item is on"),
        22: completion("The ___ of the item, including the headline"),
        23: completion("Any ___ accompanying the item"),
        24: completion("The ___ of the item, including what is made prominent"),
        25: completion("The ___ of the item"),
        26: completion("Any ___ the audience makes about the item"),
        **{
            number: matching(
                stem,
                [
                    "She will definitely look for a suitable article.",
                    "She may look for a suitable article.",
                    "She definitely won't look for an article.",
                ],
            )
            for number, stem in {
                27: "national news item",
                28: "editorial",
                29: "human-interest story",
                30: "arts",
            }.items()
        },
        31: completion("In prehistoric times, water was used to wash off ___"),
        32: completion(
            "In ancient Babylon, soap-like material was found in ___ cylinders"
        ),
        33: completion("In ancient Greece, a strigil scraper was made of ___"),
        34: completion(
            "Ancient German and Gaulish people used soap to colour their ___"
        ),
        35: completion("From about 312 BC, water was carried to Roman ___"),
        36: completion(
            "In medieval Europe, the decline in bathing contributed to the occurrence of ___"
        ),
        37: completion("In medieval Europe, ___ began to be added to soap"),
        38: completion("In 1791, Leblanc invented a way of making soda ash from ___"),
        39: completion("In the early 1800s, Chevreul turned soapmaking into a ___"),
        40: completion("From the 1800s, there was no longer a ___ on soap"),
    },
    4: {
        1: completion("Occupation: ___", "Form Completion"),
        2: completion("Reason for travel today: ___", "Form Completion"),
        3: completion("Name of station returning to: ___", "Form Completion"),
        4: completion("Type of ticket purchased: ___", "Form Completion"),
        5: completion("Cost of ticket: £___", "Form Completion"),
        6: completion("Where ticket was bought: ___", "Form Completion"),
        7: completion("Least satisfied with the ___", "Form Completion"),
        8: completion("Most satisfied with how much ___ was provided", "Form Completion"),
        9: completion(
            "Least satisfied with the lack of seats, particularly on the ___",
            "Form Completion",
        ),
        10: completion(
            "Neither satisfied nor dissatisfied with the ___ available",
            "Form Completion",
        ),
        11: map_label("café", "ABCDEFGH"),
        12: map_label("toilets", "ABCDEFGH"),
        13: map_label("formal gardens", "ABCDEFGH"),
        14: map_label("outdoor gym", "ABCDEFGH"),
        15: map_label("skateboard ramp", "ABCDEFGH"),
        16: map_label("wild flowers", "ABCDEFGH"),
        17: choices(
            "What does the speaker say about the adventure playground?",
            [
                "Children must be supervised.",
                "It costs more in winter.",
                "Some activities are only for younger children.",
                "No payment is required.",
                "It was recently expanded.",
            ],
        ),
        18: choices(
            "What does the speaker say about the adventure playground?",
            [
                "Children must be supervised.",
                "It costs more in winter.",
                "Some activities are only for younger children.",
                "No payment is required.",
                "It was recently expanded.",
            ],
        ),
        19: choices(
            "What does the speaker say about the glass houses?",
            [
                "They are closed at weekends.",
                "Volunteers are needed to work there.",
                "They were badly damaged by fire.",
                "More money is needed to repair some of the glass.",
                "Visitors can see palm trees from tropical regions.",
            ],
        ),
        20: choices(
            "What does the speaker say about the glass houses?",
            [
                "They are closed at weekends.",
                "Volunteers are needed to work there.",
                "They were badly damaged by fire.",
                "More money is needed to repair some of the glass.",
                "Visitors can see palm trees from tropical regions.",
            ],
        ),
        21: choices(
            "What did Annie discover from reading about icehouses?",
            [
                "why they were first created",
                "how the ice was kept frozen",
                "where they were located",
            ],
        ),
        22: choices(
            "What point does Annie make about refrigeration in ancient Rome?",
            [
                "It became a commercial business.",
                "It used snow from nearby.",
                "It took a long time to become popular.",
            ],
        ),
        23: choices(
            "In connection with modern refrigerators, both Annie and Jack are worried about",
            [
                "the complexity of the technology.",
                "the fact that some are disposed of irresponsibly.",
                "the large number that quickly break down.",
            ],
        ),
        24: choices(
            "What do Jack and Annie agree regarding domestic fridges?",
            [
                "They are generally good value for money.",
                "There are plenty of useful variations.",
                "They are more useful than other domestic appliances.",
            ],
        ),
        **{
            number: matching(stem, ["Annie", "Jack", "both Annie and Jack"])
            for number, stem in {
                25: "the goods that are refrigerated",
                26: "the effects on health",
                27: "the impact on food producers",
                28: "the impact on cities",
                29: "refrigerated transport",
                30: "domestic fridges",
            }.items()
        },
        31: completion(
            "People's possessions were used to measure Britain's ___"
        ),
        32: completion(
            "Developments in goods production and ___ greatly changed lives"
        ),
        33: completion(
            "The Industrial Revolution depended on new sources of ___"
        ),
        34: completion("The leading manufacturing industry was ___"),
        35: completion("New ___ made factories necessary"),
        36: completion(
            "Greater access to ___ made people more aware of goods in shops"
        ),
        37: completion("People were no longer limited to buying ___ goods"),
        38: completion("Goods were more visible inside stores due to better ___"),
        39: completion("Goods were more visible outside because ___ were bigger"),
        40: completion("Persuasive ___ became much more common"),
    },
}


QUESTION_TYPES: dict[int, list[tuple[range, str]]] = {
    1: [
        (range(1, 11), "Notes Completion"),
        (range(15, 21), "Table Completion"),
        (range(31, 41), "Notes Completion"),
    ],
    2: [
        (range(1, 5), "Table Completion"),
        (range(5, 11), "Notes Completion"),
        (range(15, 21), "Map Labelling"),
        (range(31, 41), "Notes Completion"),
    ],
    3: [
        (range(1, 11), "Notes Completion"),
        (range(21, 27), "Notes Completion"),
        (range(31, 41), "Notes Completion"),
    ],
    4: [
        (range(1, 11), "Form Completion"),
        (range(11, 17), "Map Labelling"),
        (range(31, 41), "Notes Completion"),
    ],
}


# IELTS instructions apply to question groups, but the flat API contract stores
# them on individual questions. Keep the authoritative group wording here and
# copy it onto every member so clients can recover the heading even when a
# question is rendered independently. This also repairs OCR artefacts such as
# ``ANDIOR``, ``letiers`` and instructions lost completely at page breaks.
INSTRUCTIONS: dict[int, list[tuple[range, str]]] = {
    1: [
        (
            range(1, 11),
            "Complete the notes below. Write ONE WORD AND/OR A NUMBER for each answer.",
        ),
        (range(11, 15), "Choose the correct letter, A, B or C."),
        (
            range(15, 21),
            "Complete the table below. Write ONE WORD AND/OR A NUMBER for each answer.",
        ),
        (
            range(21, 27),
            "Choose SIX answers from the box and write the correct letter, A–H, next to Questions 21–26.",
        ),
        (range(27, 29), "Choose the correct letter, A, B or C."),
        (
            range(29, 31),
            "Choose TWO letters, A–E. Which TWO experiences of sibling rivalry do the speakers agree have been valuable for them?",
        ),
        (
            range(31, 41),
            "Complete the notes below. Write ONE WORD ONLY for each answer.",
        ),
    ],
    2: [
        (
            range(1, 5),
            "Complete the table below. Write ONE WORD ONLY for each answer.",
        ),
        (
            range(5, 11),
            "Complete the notes below. Write ONE WORD ONLY for each answer.",
        ),
        (range(11, 15), "Choose the correct letter, A, B or C."),
        (
            range(15, 21),
            "Label the map below. Write the correct letter, A–I, next to Questions 15–20.",
        ),
        (
            range(21, 23),
            "Choose TWO letters, A–E. Which TWO groups of people is the display primarily intended for?",
        ),
        (
            range(23, 25),
            "Choose TWO letters, A–E. What are Cathy and Graham's TWO reasons for choosing the novelist Charles Dickens?",
        ),
        (
            range(25, 31),
            "What topic do Cathy and Graham choose to illustrate with each novel? Choose SIX answers from the box and write the correct letter, A–H, next to Questions 25–30.",
        ),
        (
            range(31, 41),
            "Complete the notes below. Write ONE WORD ONLY for each answer.",
        ),
    ],
    3: [
        (
            range(1, 11),
            "Complete the notes below. Write ONE WORD AND/OR A NUMBER for each answer.",
        ),
        (range(11, 17), "Choose the correct letter, A, B or C."),
        (
            range(17, 19),
            "Choose TWO letters, A–E. Which TWO benefits for children does Alice think are the most important?",
        ),
        (
            range(19, 21),
            "Choose TWO letters, A–E. Which TWO results of the King Street experiment surprised Alice?",
        ),
        (
            range(21, 27),
            "Complete the notes below. Write ONE WORD ONLY for each answer.",
        ),
        (
            range(27, 31),
            "What does Hazel decide to do about each type of article? Write the correct letter, A, B or C, next to Questions 27–30.",
        ),
        (
            range(31, 41),
            "Complete the notes below. Write ONE WORD ONLY for each answer.",
        ),
    ],
    4: [
        (
            range(1, 11),
            "Complete the form below. Write ONE WORD AND/OR A NUMBER for each answer.",
        ),
        (
            range(11, 17),
            "Label the map below. Write the correct letter, A–H, next to Questions 11–16.",
        ),
        (
            range(17, 19),
            "Choose TWO letters, A–E. What does the speaker say about the adventure playground?",
        ),
        (
            range(19, 21),
            "Choose TWO letters, A–E. What does the speaker say about the glass houses?",
        ),
        (range(21, 25), "Choose the correct letter, A, B or C."),
        (
            range(25, 31),
            "Who expresses each opinion? Write the correct letter, A, B or C, next to Questions 25–30.",
        ),
        (
            range(31, 41),
            "Complete the notes below. Write ONE WORD ONLY for each answer.",
        ),
    ],
}


def main() -> None:
    for test_number in range(1, 5):
        path = DATA_ROOT / f"test{test_number}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        by_number = {question["number"]: question for question in payload["questions"]}

        for number, question in by_number.items():
            question.pop("options", None)
            for numbers, question_type in QUESTION_TYPES[test_number]:
                if number in numbers:
                    question["question_type"] = question_type
                    break

        for number, replacement in CURATED[test_number].items():
            by_number[number].update(replacement)

        for numbers, instructions in INSTRUCTIONS[test_number]:
            for number in numbers:
                by_number[number]["instructions"] = instructions

        if test_number == 2:
            payload["image_s3_key"] = "listening/IELTS15/test2/minster-park.png"
        elif test_number == 4:
            payload["image_s3_key"] = (
                "listening/IELTS15/test4/croft-valley-park.png"
            )

        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
