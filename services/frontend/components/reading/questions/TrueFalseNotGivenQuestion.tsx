"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import { QuestionShell } from "./shared";

interface Props {
  question: NormalizedReadingQuestion;
  value: string;
  onChange: (value: string) => void;
}

const CHOICES = ["TRUE", "FALSE", "NOT GIVEN"] as const;

/** Fixed 3-button toggle. Unlike Multiple Choice/Matching, the option set
 * here is always the same 3 values regardless of backend data — no options
 * field or prompt-parsing dependency at all. */
export default function TrueFalseNotGivenQuestion({
  question,
  value,
  onChange,
}: Props) {
  return (
    <QuestionShell
      number={question.number}
      prompt={question.promptStem}
      instructions={question.instructions}
    >
      <div
        role="radiogroup"
        aria-label={`Question ${question.number} answer`}
        className="flex gap-2"
      >
        {CHOICES.map((choice) => {
          const selected = value === choice;
          return (
            <button
              key={choice}
              type="button"
              onClick={() => onChange(choice)}
              aria-pressed={selected}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                selected
                  ? "border-emerald-700 bg-emerald-700 text-white"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              {choice}
            </button>
          );
        })}
      </div>
    </QuestionShell>
  );
}
