"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import { QuestionShell, TextAnswerInput } from "./shared";

interface Props {
  question: NormalizedReadingQuestion;
  value: string;
  onChange: (value: string) => void;
}

/** Radio-button renderer. `question.options` is populated by
 * normalizeReadingQuestions' best-effort parse of option lines out of the
 * prompt text (there's no structured options field from the backend — see
 * the GOA-055 implementation-risk notes). Falls back to a plain text input
 * when parsing didn't find a confident option list, so the question always
 * remains answerable. */
export default function MultipleChoiceQuestion({
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
      {!question.options || question.options.length === 0 ? (
        <TextAnswerInput
          value={value}
          onChange={onChange}
          placeholder="Enter your answer (e.g. A, B, C...)"
        />
      ) : (
        <div
          role="radiogroup"
          aria-label={`Question ${question.number} options`}
          className="space-y-1.5"
        >
          {question.options.map((option, i) => {
            const letter = String.fromCharCode(65 + i);
            return (
              <label
                key={i}
                className="flex cursor-pointer items-start gap-2 text-sm text-fg-muted"
              >
                <input
                  type="radio"
                  name={`question-${question.number}`}
                  value={letter}
                  checked={value === letter}
                  onChange={() => onChange(letter)}
                  className="mt-0.5 accent-brand"
                />
                <span>
                  <span className="mr-1 font-medium">{letter}.</span>
                  {option}
                </span>
              </label>
            );
          })}
        </div>
      )}
    </QuestionShell>
  );
}
