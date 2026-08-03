"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import { QuestionShell, TextAnswerInput } from "./shared";

interface Props {
  question: NormalizedReadingQuestion;
  value: string;
  onChange: (value: string) => void;
}

export default function ShortAnswerQuestion({
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
        placeholder="Type your answer"
      />
    </QuestionShell>
  );
}
