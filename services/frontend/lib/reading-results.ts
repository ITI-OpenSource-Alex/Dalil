import type {
  NormalizedReadingQuestion,
  ReadingQuestionResult,
  ReadingUiType,
} from "@/app/types/reading";

export const READING_UI_TYPE_LABELS: Record<ReadingUiType, string> = {
  multiple_choice: "Multiple Choice",
  matching: "Matching",
  true_false_not_given: "True/False/Not Given",
  fill_in_blank: "Fill In The Blank",
  short_answer: "Short Answer",
};

export interface QuestionTypeStats {
  uiType: ReadingUiType;
  correct: number;
  total: number;
  /** 0-100. */
  percentage: number;
}

/**
 * Groups questions by their normalized UI type and computes correct/total
 * and percentage for each type actually present in the exam. Types with no
 * questions are omitted entirely (never a spurious 0/0 entry).
 *
 * Uses the same `uiType` normalizeReadingQuestions already attached to each
 * question — never re-derives the type-to-category mapping, so this can't
 * drift from what QuestionRenderer used to render the question in the first
 * place.
 */
export function calculateQuestionTypeBreakdown(
  questions: NormalizedReadingQuestion[],
  perQuestionResult: Record<string, ReadingQuestionResult>,
): QuestionTypeStats[] {
  const totals = new Map<ReadingUiType, { correct: number; total: number }>();

  for (const question of questions) {
    const entry = totals.get(question.uiType) ?? { correct: 0, total: 0 };
    entry.total += 1;

    const result = perQuestionResult[String(question.number)];
    if (result?.is_correct) {
      entry.correct += 1;
    }

    totals.set(question.uiType, entry);
  }

  return Array.from(totals.entries()).map(([uiType, { correct, total }]) => ({
    uiType,
    correct,
    total,
    percentage: total === 0 ? 0 : (correct / total) * 100,
  }));
}

/** Lowest percentage wins; ties keep the first encountered. Returns null for
 * an empty breakdown (no questions at all). */
export function findWeakestQuestionType(
  breakdown: QuestionTypeStats[],
): QuestionTypeStats | null {
  if (breakdown.length === 0) return null;

  return breakdown.reduce((weakest, current) =>
    current.percentage < weakest.percentage ? current : weakest,
  );
}
