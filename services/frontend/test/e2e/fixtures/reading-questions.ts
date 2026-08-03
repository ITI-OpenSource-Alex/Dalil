// Seeded 40-question Reading fixture for E2E testing (GOA-055).
//
// Mirrors the real backend shapes: RawReadingQuestion (app/types/reading.ts)
// for the questions, and ReadingSubmitResponse for the mocked submit result.
// Section boundaries (1-13 / 14-26 / 27-40) match
// lib/reading-sections.ts / services/exam/app/services/grading_service.py.
//
// Type distribution across the 40 questions, chosen to cover all 5 UI types
// within and across section boundaries:
//   Section 1 (1-13):  1-5 Multiple Choice, 6-13 True/False/Not Given
//   Section 2 (14-26): 14-19 Matching, 20-26 Sentence Completion (fill-in-blank)
//   Section 3 (27-40): 27-33 Short Answer, 34-40 Multiple Choice

export interface RawReadingQuestionFixture {
  number: number;
  prompt: string;
  question_type: string;
  instructions?: string | null;
  passage_number: number;
  section_number: number;
}

const PASSAGE_1 = `Coral reefs are among the most biologically diverse ecosystems on Earth, often described as the rainforests of the sea. They occupy less than one percent of the ocean floor yet support roughly a quarter of all known marine species.

Rising sea temperatures have become the dominant driver of coral bleaching worldwide. When water grows too warm, corals expel the symbiotic algae living in their tissues, turning the coral white and starving it of its main energy source.`;

const PASSAGE_2 = `The history of long-distance trade routes stretches back thousands of years, connecting distant civilizations long before modern transportation existed. Caravans crossing arid landscapes carried not only goods but also ideas, languages, and technologies between cultures.

Local communities along these routes often became centres of exchange, where merchants from different regions negotiated prices and shared knowledge of distant markets.`;

const PASSAGE_3 = `Photosynthesis is the process by which green plants convert light energy into chemical energy stored in glucose. This process occurs primarily in the chloroplasts of plant cells and depends on the pigment chlorophyll to capture light.

The Apollo 11 mission, which landed the first humans on the Moon in 1969, remains one of the most significant achievements in the history of space exploration.`;

export const READING_PASSAGES = [PASSAGE_1, PASSAGE_2, PASSAGE_3];

function multipleChoice(
  number: number,
  stem: string,
  options: string[],
  passageNumber: number,
): RawReadingQuestionFixture {
  return {
    number,
    prompt: [stem, ...options.map((o, i) => `${String.fromCharCode(65 + i)}. ${o}`)].join(
      "\n",
    ),
    question_type: "Multiple Choice",
    instructions: "Choose the correct letter, A, B, C or D.",
    passage_number: passageNumber,
    section_number: number <= 13 ? 1 : number <= 26 ? 2 : 3,
  };
}

function trueFalseNotGiven(
  number: number,
  statement: string,
  passageNumber: number,
): RawReadingQuestionFixture {
  return {
    number,
    prompt: statement,
    question_type: "True/False/Not Given",
    instructions: "Do the statements agree with the information in the passage?",
    passage_number: passageNumber,
    section_number: 1,
  };
}

function matching(
  number: number,
  stem: string,
  options: string[],
  passageNumber: number,
): RawReadingQuestionFixture {
  return {
    number,
    prompt: [stem, ...options.map((o, i) => `${String.fromCharCode(65 + i)}. ${o}`)].join(
      "\n",
    ),
    question_type: "Matching Headings",
    instructions: "Match each item to the correct heading.",
    passage_number: passageNumber,
    section_number: 2,
  };
}

function fillInBlank(
  number: number,
  prompt: string,
  passageNumber: number,
): RawReadingQuestionFixture {
  return {
    number,
    prompt,
    question_type: "Sentence Completion",
    instructions: "Complete the sentence with NO MORE THAN TWO WORDS.",
    passage_number: passageNumber,
    section_number: 2,
  };
}

function shortAnswer(
  number: number,
  prompt: string,
  passageNumber: number,
): RawReadingQuestionFixture {
  return {
    number,
    prompt,
    question_type: "Short Answer Questions",
    instructions: "Answer using NO MORE THAN THREE WORDS.",
    passage_number: passageNumber,
    section_number: 3,
  };
}

export const READING_QUESTIONS: RawReadingQuestionFixture[] = [
  // Section 1: 1-5 Multiple Choice, 6-13 True/False/Not Given
  multipleChoice(
    1,
    "According to the passage, what is the main cause of coral bleaching?",
    [
      "Rising sea temperatures",
      "Overfishing",
      "Plastic pollution",
      "Coastal development",
    ],
    1,
  ),
  multipleChoice(
    2,
    "What percentage of the ocean floor do coral reefs occupy?",
    ["Less than one percent", "About ten percent", "A quarter", "Half"],
    1,
  ),
  multipleChoice(
    3,
    "What are corals often compared to?",
    [
      "Rainforests of the sea",
      "Deserts of the sea",
      "Cities of the sea",
      "Glaciers of the sea",
    ],
    1,
  ),
  multipleChoice(
    4,
    "What do corals expel when water becomes too warm?",
    ["Symbiotic algae", "Calcium carbonate", "Mucus", "Larvae"],
    1,
  ),
  multipleChoice(
    5,
    "What happens to coral after it is bleached?",
    [
      "It is starved of its main energy source",
      "It grows faster",
      "It changes colour to bright pink",
      "It becomes more resistant to disease",
    ],
    1,
  ),
  trueFalseNotGiven(6, "Coral reefs support around a quarter of all known marine species.", 1),
  trueFalseNotGiven(7, "Coral reefs cover more than half of the ocean floor.", 1),
  trueFalseNotGiven(8, "Rising sea temperatures are the dominant driver of coral bleaching.", 1),
  trueFalseNotGiven(9, "Bleached coral turns white.", 1),
  trueFalseNotGiven(10, "Coral bleaching has no effect on coral's energy source.", 1),
  trueFalseNotGiven(11, "Symbiotic algae live inside coral tissue.", 1),
  trueFalseNotGiven(12, "Coral reefs are found only in cold-water regions.", 1),
  trueFalseNotGiven(13, "All coral species are equally vulnerable to bleaching.", 1),

  // Section 2: 14-19 Matching, 20-26 Sentence Completion
  matching(
    14,
    "Match the paragraph to the correct heading.",
    [
      "The economic impact of trade",
      "Early conservation efforts",
      "A call for international cooperation",
      "The role of local communities",
    ],
    2,
  ),
  matching(
    15,
    "Match the paragraph to the correct heading.",
    [
      "The economic impact of trade",
      "Early conservation efforts",
      "A call for international cooperation",
      "The role of local communities",
    ],
    2,
  ),
  matching(
    16,
    "Match the paragraph to the correct heading.",
    [
      "The economic impact of trade",
      "Early conservation efforts",
      "A call for international cooperation",
      "The role of local communities",
    ],
    2,
  ),
  matching(
    17,
    "Match the paragraph to the correct heading.",
    [
      "The economic impact of trade",
      "Early conservation efforts",
      "A call for international cooperation",
      "The role of local communities",
    ],
    2,
  ),
  matching(
    18,
    "Match the paragraph to the correct heading.",
    [
      "The economic impact of trade",
      "Early conservation efforts",
      "A call for international cooperation",
      "The role of local communities",
    ],
    2,
  ),
  matching(
    19,
    "Match the paragraph to the correct heading.",
    [
      "The economic impact of trade",
      "Early conservation efforts",
      "A call for international cooperation",
      "The role of local communities",
    ],
    2,
  ),
  fillInBlank(20, "Long-distance trade routes connected distant civilizations before modern ____ existed.", 2),
  fillInBlank(21, "Caravans crossed arid landscapes carrying goods, ideas, and ____.", 2),
  fillInBlank(22, "Local communities along trade routes became centres of ____.", 2),
  fillInBlank(23, "Merchants negotiated prices and shared knowledge of distant ____.", 2),
  fillInBlank(24, "Trade routes stretch back thousands of ____.", 2),
  fillInBlank(25, "Caravans carried goods, ideas, languages, and ____ between cultures.", 2),
  fillInBlank(26, "Merchants came from different ____.", 2),

  // Section 3: 27-33 Short Answer, 34-40 Multiple Choice
  shortAnswer(27, "In what year did the Apollo 11 mission land on the Moon?", 3),
  shortAnswer(28, "Which pigment does photosynthesis depend on to capture light?", 3),
  shortAnswer(29, "In which part of a plant cell does photosynthesis primarily occur?", 3),
  shortAnswer(30, "What form of energy does photosynthesis convert light into?", 3),
  shortAnswer(31, "What is the stored product of photosynthesis called?", 3),
  shortAnswer(32, "What mission first landed humans on the Moon?", 3),
  shortAnswer(33, "What do green plants use to convert light energy?", 3),
  multipleChoice(
    34,
    "What does photosynthesis convert light energy into?",
    ["Chemical energy stored in glucose", "Heat", "Sound", "Kinetic energy"],
    3,
  ),
  multipleChoice(
    35,
    "Where does photosynthesis primarily occur?",
    ["Chloroplasts", "Mitochondria", "The nucleus", "The cell wall"],
    3,
  ),
  multipleChoice(
    36,
    "What pigment captures light for photosynthesis?",
    ["Chlorophyll", "Melanin", "Carotene", "Haemoglobin"],
    3,
  ),
  multipleChoice(
    37,
    "When did the Apollo 11 mission take place?",
    ["1969", "1959", "1979", "1989"],
    3,
  ),
  multipleChoice(
    38,
    "What is considered one of the most significant achievements in space exploration?",
    [
      "The Apollo 11 Moon landing",
      "The first satellite launch",
      "The first space station",
      "The first Mars rover",
    ],
    3,
  ),
  multipleChoice(
    39,
    "What did the Apollo 11 mission achieve for the first time?",
    [
      "Landing humans on the Moon",
      "Orbiting Mars",
      "Launching a reusable rocket",
      "Building a space station",
    ],
    3,
  ),
  multipleChoice(
    40,
    "What type of cell structure hosts photosynthesis?",
    ["Chloroplasts", "Ribosomes", "Golgi bodies", "Vacuoles"],
    3,
  ),
];

/** Question numbers that are marked correct in the mocked submit response,
 * chosen to give a clean, verifiable per-type and per-section breakdown:
 * Multiple Choice 10/12, True/False/Not Given 6/8, Matching 4/6,
 * Fill-in-Blank 5/7, Short Answer 3/7 (the deliberate weakest type) -> 28/40
 * overall, section_1 10/13, section_2 9/13, section_3 9/14. */
const CORRECT_QUESTION_NUMBERS = new Set([
  1, 2, 3, 4, // Multiple Choice (section 1): 4/5
  6, 7, 8, 9, 10, 11, // True/False/Not Given: 6/8
  14, 15, 16, 17, // Matching: 4/6
  20, 21, 22, 23, 24, // Fill-in-Blank: 5/7
  27, 28, 29, // Short Answer: 3/7
  34, 35, 36, 37, 38, 39, // Multiple Choice (section 3): 6/7
]);

export function buildReadingSubmitResponse(answers: Record<string, string>) {
  const per_question_result: Record<
    string,
    { submitted_answer: string; correct_answer: string; is_correct: boolean }
  > = {};

  for (const question of READING_QUESTIONS) {
    const key = String(question.number);
    const isCorrect = CORRECT_QUESTION_NUMBERS.has(question.number);
    const submitted = answers[key] ?? "";
    per_question_result[key] = {
      submitted_answer: submitted,
      correct_answer: isCorrect && submitted ? submitted : "REFERENCE_ANSWER",
      is_correct: isCorrect,
    };
  }

  return {
    raw_score: CORRECT_QUESTION_NUMBERS.size,
    band_score: 6.5,
    per_question_result,
    section_breakdown: {
      section_1: { correct: 10, total: 13 },
      section_2: { correct: 9, total: 13 },
      section_3: { correct: 9, total: 14 },
    },
  };
}
