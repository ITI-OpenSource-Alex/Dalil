import type {
  NormalizedReadingQuestion,
  ReadingAnswers,
} from "@/app/types/reading";

/** Same rule as QuestionNavSidebar / the old footer: non-empty after trim. */
export function isAnswered(
  answers: ReadingAnswers,
  questionNumber: number,
): boolean {
  return Boolean(answers[String(questionNumber)]?.trim());
}

export function countAnswered(
  questions: Pick<NormalizedReadingQuestion, "number">[],
  answers: ReadingAnswers,
): number {
  return questions.filter((q) => isAnswered(answers, q.number)).length;
}

export interface ReadingProgress {
  section: 1 | 2 | 3;
  sectionAnswered: number;
  sectionTotal: number;
  examAnswered: number;
  examTotal: number;
}

/**
 * Dual progress for the Reading footer: active-section counts plus
 * exam-wide totals. Section totals come from the questions actually in
 * that section (not hard-coded 13), so incomplete fixtures stay honest.
 */
export function getReadingProgress({
  questions,
  answers,
  activeSection,
}: {
  questions: Pick<NormalizedReadingQuestion, "number" | "section">[];
  answers: ReadingAnswers;
  activeSection: 1 | 2 | 3;
}): ReadingProgress {
  const sectionQuestions = questions.filter((q) => q.section === activeSection);

  return {
    section: activeSection,
    sectionAnswered: countAnswered(sectionQuestions, answers),
    sectionTotal: sectionQuestions.length,
    examAnswered: countAnswered(questions, answers),
    examTotal: questions.length,
  };
}

/** Footer / a11y label: `Section 1: 3/13 · Exam: 12/40` */
export function formatReadingProgress(progress: ReadingProgress): string {
  const {
    section,
    sectionAnswered,
    sectionTotal,
    examAnswered,
    examTotal,
  } = progress;
  return `Section ${section}: ${sectionAnswered}/${sectionTotal} · Exam: ${examAnswered}/${examTotal}`;
}
