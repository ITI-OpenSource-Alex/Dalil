import { describe, expect, it } from "vitest";
import {
  calculateQuestionTypeBreakdown,
  findWeakestQuestionType,
} from "./reading-results";
import type {
  NormalizedReadingQuestion,
  ReadingQuestionResult,
} from "@/app/types/reading";

function question(
  number: number,
  uiType: NormalizedReadingQuestion["uiType"],
): NormalizedReadingQuestion {
  return {
    number,
    prompt: `Question ${number}`,
    promptStem: `Question ${number}`,
    rawQuestionType: uiType,
    uiType,
    instructions: null,
    passageNumber: 1,
    section: 1,
  };
}

function result(isCorrect: boolean): ReadingQuestionResult {
  return {
    submitted_answer: "x",
    correct_answer: "x",
    is_correct: isCorrect,
  };
}

describe("calculateQuestionTypeBreakdown", () => {
  it("calculates the correct percentage for each question type present", () => {
    // Matches the ticket's own example shape: 9/10, 7/8, 4/8, 5/6, 3/4.
    const questions: NormalizedReadingQuestion[] = [
      ...Array.from({ length: 10 }, (_, i) => question(i + 1, "multiple_choice")),
      ...Array.from({ length: 8 }, (_, i) => question(i + 11, "matching")),
    ];

    const perQuestionResult: Record<string, ReadingQuestionResult> = {};
    // 9/10 correct multiple choice
    for (let i = 1; i <= 9; i++) perQuestionResult[String(i)] = result(true);
    perQuestionResult["10"] = result(false);
    // 7/8 correct matching
    for (let i = 11; i <= 17; i++) perQuestionResult[String(i)] = result(true);
    perQuestionResult["18"] = result(false);

    const breakdown = calculateQuestionTypeBreakdown(questions, perQuestionResult);

    const mc = breakdown.find((b) => b.uiType === "multiple_choice");
    const matching = breakdown.find((b) => b.uiType === "matching");

    expect(mc).toEqual({
      uiType: "multiple_choice",
      correct: 9,
      total: 10,
      percentage: 90,
    });
    expect(matching).toEqual({
      uiType: "matching",
      correct: 7,
      total: 8,
      percentage: 87.5,
    });
  });

  it("omits question types that have zero questions in the exam", () => {
    const questions = [question(1, "short_answer")];
    const perQuestionResult = { "1": result(true) };

    const breakdown = calculateQuestionTypeBreakdown(questions, perQuestionResult);

    expect(breakdown).toHaveLength(1);
    expect(breakdown[0].uiType).toBe("short_answer");
  });

  it("counts an unanswered question (missing from per_question_result) as incorrect, not a crash", () => {
    const questions = [question(1, "true_false_not_given"), question(2, "true_false_not_given")];
    const perQuestionResult = { "1": result(true) }; // question 2 never answered/graded

    const breakdown = calculateQuestionTypeBreakdown(questions, perQuestionResult);

    expect(breakdown[0]).toEqual({
      uiType: "true_false_not_given",
      correct: 1,
      total: 2,
      percentage: 50,
    });
  });

  it("returns an empty array for no questions", () => {
    expect(calculateQuestionTypeBreakdown([], {})).toEqual([]);
  });
});

describe("findWeakestQuestionType", () => {
  it("picks the lowest percentage among the ticket's example breakdown", () => {
    // Multiple Choice: 9/10 (90%), Matching: 7/8 (87.5%), TFNG: 4/8 (50%),
    // Fill Blank: 5/6 (83.3%), Short Answer: 3/4 (75%) -> TFNG is weakest.
    const breakdown = [
      { uiType: "multiple_choice" as const, correct: 9, total: 10, percentage: 90 },
      { uiType: "matching" as const, correct: 7, total: 8, percentage: 87.5 },
      { uiType: "true_false_not_given" as const, correct: 4, total: 8, percentage: 50 },
      { uiType: "fill_in_blank" as const, correct: 5, total: 6, percentage: (5 / 6) * 100 },
      { uiType: "short_answer" as const, correct: 3, total: 4, percentage: 75 },
    ];

    expect(findWeakestQuestionType(breakdown)?.uiType).toBe(
      "true_false_not_given",
    );
  });

  it("returns null for an empty breakdown", () => {
    expect(findWeakestQuestionType([])).toBeNull();
  });
});
