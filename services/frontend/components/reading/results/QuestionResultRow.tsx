"use client";

import type {
  NormalizedReadingQuestion,
  ReadingQuestionResult,
} from "@/app/types/reading";

interface Props {
  question: NormalizedReadingQuestion;
  result: ReadingQuestionResult | undefined;
}

/**
 * Single question's result: user answer, correct answer, correct/incorrect
 * styling, and a passage location hint. The hint is "Passage N" —
 * `passage_number` is the only location signal the backend provides per
 * question (no paragraph/line reference exists in the schema).
 */
export default function QuestionResultRow({ question, result }: Props) {
  if (!result) {
    return null;
  }

  return (
    <div
      data-testid={`result-row-${question.number}`}
      data-correct={result.is_correct}
      className={`rounded-xl border p-4 ${
        result.is_correct
          ? "border-emerald-200 bg-emerald-50"
          : "border-red-200 bg-red-50"
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-gray-900">
          <span className="mr-2">{question.number}.</span>
          {question.promptStem}
        </p>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
            result.is_correct
              ? "bg-emerald-600 text-white"
              : "bg-red-600 text-white"
          }`}
        >
          {result.is_correct ? "Correct" : "Incorrect"}
        </span>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <p>
          <span className="text-gray-500">Your answer: </span>
          <span
            data-testid={`result-user-answer-${question.number}`}
            className="font-semibold text-gray-900"
          >
            {result.submitted_answer || "(no answer)"}
          </span>
        </p>
        <p>
          <span className="text-gray-500">Correct answer: </span>
          <span
            data-testid={`result-correct-answer-${question.number}`}
            className="font-semibold text-gray-900"
          >
            {result.correct_answer}
          </span>
        </p>
        {question.passageNumber != null && (
          <p data-testid={`result-passage-hint-${question.number}`}>
            <span className="text-gray-500">Location: </span>
            <span className="font-medium text-gray-700">
              Passage {question.passageNumber}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}
