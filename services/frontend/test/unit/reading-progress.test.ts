import { describe, expect, it } from "vitest";
import {
  countAnswered,
  formatReadingProgress,
  getReadingProgress,
  isAnswered,
} from "@/lib/reading-progress";
import type { NormalizedReadingQuestion } from "@/app/types/reading";

function q(
  number: number,
  section: 1 | 2 | 3,
): Pick<NormalizedReadingQuestion, "number" | "section"> {
  return { number, section };
}

const QUESTIONS = [
  q(1, 1),
  q(2, 1),
  q(3, 1),
  q(14, 2),
  q(15, 2),
  q(27, 3),
];

describe("isAnswered", () => {
  it("returns false for missing or whitespace-only answers", () => {
    expect(isAnswered({}, 1)).toBe(false);
    expect(isAnswered({ "1": "" }, 1)).toBe(false);
    expect(isAnswered({ "1": "   " }, 1)).toBe(false);
  });

  it("returns true for non-empty trimmed answers", () => {
    expect(isAnswered({ "1": "B" }, 1)).toBe(true);
    expect(isAnswered({ "1": "  yes  " }, 1)).toBe(true);
  });
});

describe("countAnswered", () => {
  it("counts only questions in the given list", () => {
    const answers = { "1": "A", "14": "C", "99": "ignored" };
    expect(countAnswered(QUESTIONS, answers)).toBe(2);
  });
});

describe("getReadingProgress", () => {
  it("returns zeros when nothing is answered", () => {
    expect(
      getReadingProgress({
        questions: QUESTIONS,
        answers: {},
        activeSection: 1,
      }),
    ).toEqual({
      section: 1,
      sectionAnswered: 0,
      sectionTotal: 3,
      examAnswered: 0,
      examTotal: 6,
    });
  });

  it("counts section-only answers against the active section", () => {
    expect(
      getReadingProgress({
        questions: QUESTIONS,
        answers: { "1": "A", "2": "B" },
        activeSection: 1,
      }),
    ).toEqual({
      section: 1,
      sectionAnswered: 2,
      sectionTotal: 3,
      examAnswered: 2,
      examTotal: 6,
    });
  });

  it("keeps exam total when answers span sections; section follows active tab", () => {
    const answers = { "1": "A", "14": "C", "27": "1969" };

    expect(
      getReadingProgress({
        questions: QUESTIONS,
        answers,
        activeSection: 1,
      }),
    ).toMatchObject({
      sectionAnswered: 1,
      sectionTotal: 3,
      examAnswered: 3,
      examTotal: 6,
    });

    expect(
      getReadingProgress({
        questions: QUESTIONS,
        answers,
        activeSection: 2,
      }),
    ).toMatchObject({
      section: 2,
      sectionAnswered: 1,
      sectionTotal: 2,
      examAnswered: 3,
    });

    expect(
      getReadingProgress({
        questions: QUESTIONS,
        answers,
        activeSection: 3,
      }),
    ).toMatchObject({
      section: 3,
      sectionAnswered: 1,
      sectionTotal: 1,
      examAnswered: 3,
    });
  });

  it("does not count whitespace-only answers", () => {
    expect(
      getReadingProgress({
        questions: QUESTIONS,
        answers: { "1": "   ", "14": "C" },
        activeSection: 1,
      }),
    ).toMatchObject({
      sectionAnswered: 0,
      examAnswered: 1,
    });
  });
});

describe("formatReadingProgress", () => {
  it("formats the dual footer label", () => {
    expect(
      formatReadingProgress({
        section: 1,
        sectionAnswered: 5,
        sectionTotal: 13,
        examAnswered: 5,
        examTotal: 40,
      }),
    ).toBe("Section 1: 5/13 · Exam: 5/40");
  });
});
