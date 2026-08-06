"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import type { ReadingAnswers } from "@/app/types/reading";

interface Props {
  questions: NormalizedReadingQuestion[];
  answers: ReadingAnswers;
  activeQuestionNumber: number | null;
  onJump: (questionNumber: number) => void;
}

/** Numbered-circle navigator: filled = answered, empty = unanswered,
 * clicking jumps directly to that question (across sections if needed —
 * ReadingExam's jump handler switches the active section as part of the
 * jump). Spans all 40 questions regardless of which section tab is
 * currently active, so overall progress is always visible. */
export default function QuestionNavSidebar({
  questions,
  answers,
  activeQuestionNumber,
  onJump,
}: Props) {
  return (
    <nav
      data-testid="question-nav-sidebar"
      aria-label="Question navigation"
      className="grid grid-cols-5 gap-2 p-4"
    >
      {questions.map((question) => {
        const answered = Boolean(answers[String(question.number)]?.trim());
        const active = question.number === activeQuestionNumber;

        return (
          <button
            key={question.number}
            type="button"
            data-testid={`nav-circle-${question.number}`}
            data-answered={answered}
            onClick={() => onJump(question.number)}
            aria-label={`Question ${question.number}${answered ? ", answered" : ", unanswered"}`}
            aria-current={active ? "true" : undefined}
            className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted ${
              active
                ? "border-brand ring-2 ring-brand-muted"
                : "border-border-strong"
            } ${
              answered
                ? "bg-brand text-fg-on-brand"
                : "bg-surface text-fg-muted hover:bg-canvas-subtle"
            }`}
          >
            {question.number}
          </button>
        );
      })}
    </nav>
  );
}
