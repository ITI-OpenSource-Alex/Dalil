"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import type { ReadingAnswers } from "@/app/types/reading";
import { isAnswered } from "@/lib/reading-progress";
import {
  navCircleAriaLabel,
  navCircleClassName,
  navLegendSwatchClassName,
} from "@/lib/question-nav-state";

interface Props {
  questions: NormalizedReadingQuestion[];
  answers: ReadingAnswers;
  activeQuestionNumber: number | null;
  onJump: (questionNumber: number) => void;
}

const LEGEND_ITEMS = [
  { kind: "current" as const, label: "Current" },
  { kind: "answered" as const, label: "Answered" },
  { kind: "unanswered" as const, label: "Unanswered" },
];

/** Numbered-circle navigator: filled = answered, empty = unanswered,
 * ring = current (stacks with either). Clicking jumps directly to that
 * question (across sections if needed — ReadingExam's jump handler
 * switches the active section as part of the jump). Spans all questions
 * regardless of which section tab is active. */
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
      className="flex min-h-0 flex-col p-3"
    >
      <div className="grid grid-cols-4 justify-items-center gap-1.5">
        {questions.map((question) => {
          const answered = isAnswered(answers, question.number);
          const active = question.number === activeQuestionNumber;

          return (
            <button
              key={question.number}
              type="button"
              data-testid={`nav-circle-${question.number}`}
              data-answered={answered}
              data-current={active || undefined}
              onClick={() => onJump(question.number)}
              aria-label={navCircleAriaLabel({
                questionNumber: question.number,
                answered,
                active,
              })}
              aria-current={active ? "true" : undefined}
              className={navCircleClassName({ answered, active })}
            >
              {question.number}
            </button>
          );
        })}
      </div>

      <ul
        data-testid="question-nav-legend"
        className="mt-3 space-y-1.5 border-t border-border pt-3"
        aria-label="Question status legend"
      >
        {LEGEND_ITEMS.map(({ kind, label }) => (
          <li
            key={kind}
            className="flex items-center gap-2 text-[10px] leading-none text-fg-subtle"
          >
            <span
              className={navLegendSwatchClassName(kind)}
              aria-hidden="true"
            />
            {label}
          </li>
        ))}
      </ul>
    </nav>
  );
}
