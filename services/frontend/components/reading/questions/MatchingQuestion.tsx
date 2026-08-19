"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import { QuestionShell, TextAnswerInput } from "./shared";

interface Props {
  question: NormalizedReadingQuestion;
  value: string;
  onChange: (value: string) => void;
}

/** Dropdown renderer for Matching questions (GOA-055 offers dropdown OR
 * dnd-kit drag-and-drop; dropdown was chosen — see the implementation-risk
 * notes: Matching has zero real examples in currently-ingested data to
 * validate a drag-and-drop options contract against, and a dropdown's
 * selected value maps directly onto the backend's flat string-equality
 * grading with no extra serialization step). Falls back to free text when
 * no option list could be parsed from the prompt. */
export default function MatchingQuestion({ question, value, onChange }: Props) {
  const isMapLabelling = question.rawQuestionType
    .toLowerCase()
    .includes("map labelling");

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
          placeholder="Enter the matching letter/heading"
        />
      ) : (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={`Question ${question.number} match`}
          className="w-full max-w-sm rounded-lg border border-border-strong bg-surface px-3 py-1.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand-muted"
        >
          <option value="">Select a match…</option>
          {question.options.map((option, i) => {
            const letter = String.fromCharCode(65 + i);
            const optionValue = isMapLabelling ? option : letter;
            return (
              <option key={i} value={optionValue}>
                {isMapLabelling ? `Location ${option}` : `${letter}. ${option}`}
              </option>
            );
          })}
        </select>
      )}
    </QuestionShell>
  );
}
