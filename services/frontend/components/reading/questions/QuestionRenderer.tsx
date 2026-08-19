"use client";

import type { NormalizedReadingQuestion } from "@/app/types/reading";
import MultipleChoiceQuestion from "./MultipleChoiceQuestion";
import MatchingQuestion from "./MatchingQuestion";
import TrueFalseNotGivenQuestion from "./TrueFalseNotGivenQuestion";
import FillInBlankQuestion from "./FillInBlankQuestion";
import ShortAnswerQuestion from "./ShortAnswerQuestion";

interface Props {
  question: NormalizedReadingQuestion;
  value: string;
  onChange: (value: string) => void;
}

/** Dispatches on the already-normalized `uiType` (see
 * normalizeReadingQuestions.ts) — never re-derives a type mapping here, so
 * this and QuestionTypeBreakdown can't disagree about what a question is. */
export default function QuestionRenderer({ question, value, onChange }: Props) {
  switch (question.uiType) {
    case "multiple_choice":
      return (
        <MultipleChoiceQuestion
          question={question}
          value={value}
          onChange={onChange}
        />
      );
    case "matching":
      return (
        <MatchingQuestion question={question} value={value} onChange={onChange} />
      );
    case "true_false_not_given":
      return (
        <TrueFalseNotGivenQuestion
          question={question}
          value={value}
          onChange={onChange}
        />
      );
    case "fill_in_blank":
      return (
        <FillInBlankQuestion
          question={question}
          value={value}
          onChange={onChange}
        />
      );
    case "short_answer":
      return (
        <ShortAnswerQuestion
          question={question}
          value={value}
          onChange={onChange}
        />
      );
  }
}
