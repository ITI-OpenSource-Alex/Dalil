"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import { QuestionShell, TextAnswerInput } from "./shared";

interface Props {
  question: NormalizedReadingQuestion;
  value: string;
  onChange: (value: string) => void;
}

/** Text-input renderer for Completion-style questions (Sentence/Summary/
 * Notes Completion — bucketed to fill_in_blank by normalizeReadingQuestions).
 * Real prompt text has no confirmed machine-readable blank-position marker,
 * so this renders the full sentence/passage-excerpt as context above a
 * single input, rather than attempting to interpolate the input mid-text —
 * see the GOA-055 implementation notes for why. */
export default function FillInBlankQuestion({
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
      <TextAnswerInput
        value={value}
        onChange={onChange}
        placeholder="Fill in the blank"
      />
    </QuestionShell>
  );
}
