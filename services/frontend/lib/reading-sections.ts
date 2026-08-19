// Reading questions carry no `section` field from the backend — grouping
// into Section 1/2/3 exists only as a fixed numeric-range table used for
// grading, in services/exam/app/services/grading_service.py:
//
//   READING_SECTION_RANGES = {
//     "section_1": (1, 13),
//     "section_2": (14, 26),
//     "section_3": (27, 40),
//   }
//
// This file must stay byte-for-byte in sync with those ranges: if the
// frontend buckets a question differently than the backend, the section tabs
// shown while taking the exam will disagree with the section_breakdown the
// backend returns on submit.

export const READING_SECTION_RANGES: Record<1 | 2 | 3, [number, number]> = {
  1: [1, 13],
  2: [14, 26],
  3: [27, 40],
};

export function sectionForQuestionNumber(questionNumber: number): 1 | 2 | 3 {
  for (const section of [1, 2, 3] as const) {
    const [start, end] = READING_SECTION_RANGES[section];
    if (questionNumber >= start && questionNumber <= end) {
      return section;
    }
  }
  // Real Cambridge Reading tests are always 40 questions across these three
  // ranges; a question number outside 1-40 indicates malformed data, not a
  // valid fourth section. Section 3 is the least-wrong fallback rather than
  // throwing, since a single malformed question shouldn't crash the whole
  // exam UI.
  return 3;
}
