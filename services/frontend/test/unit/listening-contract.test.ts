import { describe, expect, it } from "vitest";
import { normalizeListeningQuestions } from "@/lib/listening-api";
import type { RawReadingQuestion } from "@/app/types/reading";

describe("Listening question contract", () => {
  it("preserves structured options supplied by the exam service", () => {
    const raw = [
      {
        number: 11,
        prompt: "According to the speaker, which statement is correct?",
        question_type: "Multiple Choice",
        instructions: "Choose the correct letter, A, B or C.",
        passage_number: null,
        section_number: 2,
        options: ["The oldest company", "The widest range", "The most customers"],
      },
    ] as Array<RawReadingQuestion & { options: string[] }>;

    const normalized = normalizeListeningQuestions(raw);

    expect(normalized[0]).toMatchObject({
      number: 11,
      section: 2,
      uiType: "multiple_choice",
      options: raw[0].options,
      promptStem: raw[0].prompt,
    });
  });
});
