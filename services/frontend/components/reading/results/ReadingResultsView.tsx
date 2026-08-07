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
  /** "Passage" for Reading, "Section" for Listening. Forwarded per row. */
  locationLabel?: string;
}

/**
 * Full results view for the question-based exam skills: overall score,
 * per-question review (user vs correct answer, green/red, location hint),
 * question-type breakdown with the weakest type flagged, section progress
 * bars, and a "practice again" CTA.
 *
 * Listening reuses this view rather than duplicating it — the two payloads
 * are the same shape, so everything that differs between the skills is a
 * prop, and the defaults keep Reading's call sites unchanged.
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
  locationLabel,
}: Props) {
  const router = useRouter();

  const sortedQuestions = [...questions].sort((a, b) => a.number - b.number);

  return (
    <div data-testid={resultTestId} className="space-y-6">
      <div className="rounded-3xl border border-border bg-surface p-8 shadow-2xs">
        <span className="rounded-full border border-brand-border bg-brand-subtle px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-brand-fg">
          {title}
        </span>
        <div className="mt-4 flex items-baseline gap-6">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-fg-subtle">
              Overall Band
            </p>
            <p
              data-testid={bandScoreTestId}
              className="text-4xl font-serif font-bold text-brand-fg"
            >
              {result.band_score}
            </p>
          </div>
          <p className="text-sm text-fg-subtle">
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

      <div className="rounded-2xl border border-border bg-surface p-6 shadow-2xs">
        <h3 className="mb-4 text-sm font-bold text-fg">
          Question-by-Question Review
        </h3>
        <div className="space-y-3">
          {sortedQuestions.map((question) => (
            <QuestionResultRow
              key={question.number}
              question={question}
              result={result.per_question_result[String(question.number)]}
              locationLabel={locationLabel}
            />
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          data-testid={buttonTestId}
          onClick={() => router.push(buttonHref)}
          className="rounded-full bg-brand px-5 py-2.5 text-xs font-semibold text-fg-on-brand transition hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          {buttonLabel}
        </button>
      </div>
    </div>
  );
}
