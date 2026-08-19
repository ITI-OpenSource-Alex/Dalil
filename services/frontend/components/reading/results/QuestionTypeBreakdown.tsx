"use client";

import {
  READING_UI_TYPE_LABELS,
  calculateQuestionTypeBreakdown,
  findWeakestQuestionType,
} from "@/lib/reading-results";

interface Props {
  questions: Array<{ number: number; uiType?: string }>;
  perQuestionResult: Record<string, { is_correct?: boolean }>;
  questionTypeLabels?: Record<string, string>;
}

/** Question-type breakdown panel (e.g. "Multiple Choice: 9/10"), with the
 * weakest type highlighted. All the grouping/percentage math lives in
 * lib/reading-results.ts as plain, independently unit-tested functions. */
export default function QuestionTypeBreakdown({
  questions,
  perQuestionResult,
  questionTypeLabels,
}: Props) {
  const breakdown = calculateQuestionTypeBreakdown(
    questions,
    perQuestionResult,
  );
  const weakest = findWeakestQuestionType(breakdown);

  return (
    <div
      data-testid="question-type-breakdown"
      className="rounded-2xl border border-border bg-surface p-6 shadow-2xs"
    >
      <h3 className="mb-4 text-sm font-bold text-fg">
        Question Type Breakdown
      </h3>

      <ul className="space-y-2">
        {breakdown.map((stat) => {
          const isWeakest = weakest?.uiType === stat.uiType;
          return (
            <li
              key={stat.uiType}
              data-testid={`breakdown-${stat.uiType}`}
              data-weakest={isWeakest}
              className={`flex items-center justify-between rounded-lg px-3 py-2 text-xs ${
                isWeakest
                  ? "border border-warning-border bg-warning-subtle"
                  : "bg-canvas-subtle"
              }`}
            >
              <span
                className={`font-medium ${isWeakest ? "text-warning-fg" : "text-fg-muted"}`}
              >
                {questionTypeLabels?.[stat.uiType] ??
                  READING_UI_TYPE_LABELS[
                    stat.uiType as keyof typeof READING_UI_TYPE_LABELS
                  ] ??
                  stat.uiType}
                {isWeakest && (
                  <span className="ml-2 rounded-full bg-warning px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">
                    Weakest
                  </span>
                )}
              </span>
              <span className="font-semibold text-fg">
                {stat.correct}/{stat.total}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
