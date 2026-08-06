"use client";

import { useRouter } from "next/navigation";
import QuestionResultRow from "./QuestionResultRow";
import QuestionTypeBreakdown from "./QuestionTypeBreakdown";
import SectionBreakdownBars from "./SectionBreakdownBars";

interface Props {
  result: {
    band_score: number;
    raw_score: number;
    per_question_result: Record<
      string,
      { submitted_answer: string; correct_answer: string; is_correct: boolean }
    >;
    section_breakdown: Record<string, { correct: number; total: number }>;
  };
  questions: Array<{
    number: number;
    promptStem: string;
    passageNumber?: number | null;
    uiType?: string;
  }>;
  title?: string;
  buttonLabel?: string;
  buttonHref?: string;
  resultTestId?: string;
  bandScoreTestId?: string;
  buttonTestId?: string;
  questionTypeLabels?: Record<string, string>;
  sections?: Array<{ key: string; label: string }>;
}

/**
 * Full Reading results view: overall score, per-question review (user vs
 * correct answer, green/red, passage hint), question-type breakdown with
 * the weakest type flagged, section progress bars, and "Practice Reading
 * Again".
 */
export default function ReadingResultsView({
  result,
  questions,
  title = "Reading Results",
  buttonLabel = "Practice Reading Again",
  buttonHref = "/exam",
  resultTestId = "reading-results-view",
  bandScoreTestId = "reading-band-score",
  buttonTestId = "practice-reading-again-button",
  questionTypeLabels,
  sections,
}: Props) {
  const router = useRouter();

  const sortedQuestions = [...questions].sort((a, b) => a.number - b.number);

  return (
    <div data-testid={resultTestId} className="space-y-6">
      <div className="rounded-3xl border border-gray-200/80 bg-white p-8 shadow-2xs">
        <span className="rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#0d4d3a]">
          {title}
        </span>
        <div className="mt-4 flex items-baseline gap-6">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">
              Overall Band
            </p>
            <p
              data-testid={bandScoreTestId}
              className="text-4xl font-serif font-bold text-[#0d4d3a]"
            >
              {result.band_score}
            </p>
          </div>
          <p className="text-sm text-gray-500">
            Raw score: {result.raw_score}/{questions.length}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <QuestionTypeBreakdown
          questions={questions}
          perQuestionResult={result.per_question_result}
          questionTypeLabels={questionTypeLabels}
        />
        <SectionBreakdownBars
          sectionBreakdown={result.section_breakdown}
          sections={sections}
        />
      </div>

      <div className="rounded-2xl border border-gray-200/80 bg-white p-6 shadow-2xs">
        <h3 className="mb-4 text-sm font-bold text-gray-900">
          Question-by-Question Review
        </h3>
        <div className="space-y-3">
          {sortedQuestions.map((question) => (
            <QuestionResultRow
              key={question.number}
              question={question}
              result={result.per_question_result[String(question.number)]}
            />
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          data-testid={buttonTestId}
          onClick={() => router.push(buttonHref)}
          className="rounded-full bg-[#0d4d3a] px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-[#09382a]"
        >
          {buttonLabel}
        </button>
      </div>
    </div>
  );
}
