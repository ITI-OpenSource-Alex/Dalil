"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import type { ExamSessionResponse } from "@/lib/exam-api";
import {
  extractRawQuestions,
  splitPassages,
  submitReadingSession,
} from "@/lib/reading-api";
import { normalizeReadingQuestions } from "@/lib/normalizeReadingQuestions";
import type {
  NormalizedReadingQuestion,
  RawReadingQuestion,
  ReadingAnswers,
  ReadingSubmitResponse,
} from "@/app/types/reading";
import {
  formatReadingProgress,
  getReadingProgress,
} from "@/lib/reading-progress";
import PassagePanel from "./PassagePanel";
import SectionTabs from "./SectionTabs";
import QuestionNavSidebar from "./QuestionNavSidebar";
import SubmitConfirmModal from "./SubmitConfirmModal";
import QuestionRenderer from "./questions/QuestionRenderer";

interface ReadingExamState {
  questions: NormalizedReadingQuestion[];
  passages: string[];
  answers: ReadingAnswers;
  activeSection: 1 | 2 | 3;
  activeQuestionNumber: number | null;
  submitting: boolean;
  submitError: string | null;
}

type ReadingExamAction =
  | { type: "ANSWER_CHANGED"; questionNumber: number; value: string }
  | { type: "SECTION_CHANGED"; section: 1 | 2 | 3 }
  | { type: "QUESTION_JUMP"; questionNumber: number; section: 1 | 2 | 3 }
  | { type: "SUBMIT_STARTED" }
  | { type: "SUBMIT_FAILED"; error: string };

function buildInitialState(session: ExamSessionResponse): ReadingExamState {
  const rawQuestions = extractRawQuestions(
    session,
  ) as unknown as RawReadingQuestion[];
  const questions = normalizeReadingQuestions(rawQuestions);
  const passages = splitPassages(session.questions[0]?.passage_text);

  return {
    questions,
    passages,
    // Flat map keyed by absolute question number across all sections — a
    // section switch never touches this, so every answer survives it.
    answers: {},
    activeSection: 1,
    activeQuestionNumber: questions[0]?.number ?? null,
    submitting: false,
    submitError: null,
  };
}

function reducer(
  state: ReadingExamState,
  action: ReadingExamAction,
): ReadingExamState {
  switch (action.type) {
    case "ANSWER_CHANGED":
      return {
        ...state,
        answers: {
          ...state.answers,
          [String(action.questionNumber)]: action.value,
        },
      };

    case "SECTION_CHANGED": {
      const firstInSection = state.questions.find(
        (q) => q.section === action.section,
      );
      return {
        ...state,
        activeSection: action.section,
        activeQuestionNumber: firstInSection?.number ?? null,
      };
    }

    case "QUESTION_JUMP":
      return {
        ...state,
        activeSection: action.section,
        activeQuestionNumber: action.questionNumber,
      };

    case "SUBMIT_STARTED":
      return { ...state, submitting: true, submitError: null };

    case "SUBMIT_FAILED":
      return { ...state, submitting: false, submitError: action.error };
  }
}

interface ReadingExamProps {
  sessionId: string;
  session: ExamSessionResponse;
  onSubmitted: (
    result: ReadingSubmitResponse,
    questions: NormalizedReadingQuestion[],
  ) => void;
  /**
   * Bumped by the shell when the exam timer reaches zero. The shell's own
   * timeout handler is hardcoded to Writing's submit shape (executeSubmission
   * in app/exam/shell/page.tsx), so it can't be reused directly here —
   * incrementing this instead triggers ReadingExam's own submit, skipping
   * the confirmation modal exactly like a normal timeout auto-submit should.
   */
  forceSubmitSignal?: number;
}

/**
 * Top-level Reading exam UI (GOA-055). Owns the single useReducer instance
 * covering session/answers/navigation. Passage highlighting is
 * *deliberately excluded* from this state — it lives entirely inside
 * PassagePanel's own usePassageHighlights hook, so it can never be part of
 * what handleConfirmSubmit sends, and a highlight interaction never
 * re-renders the (much heavier) question panel.
 */
export default function ReadingExam({
  sessionId,
  session,
  onSubmitted,
  forceSubmitSignal,
}: ReadingExamProps) {
  const [state, dispatch] = useReducer(reducer, session, buildInitialState);
  const [showSubmitModal, setShowSubmitModal] = useState(false);

  const activeQuestions = state.questions.filter(
    (q) => q.section === state.activeSection,
  );
  const activePassage = state.passages[state.activeSection - 1] ?? "";

  const unansweredCount = state.questions.filter(
    (q) => !state.answers[String(q.number)]?.trim(),
  ).length;
  const progress = getReadingProgress({
    questions: state.questions,
    answers: state.answers,
    activeSection: state.activeSection,
  });

  const handleJump = (questionNumber: number) => {
    const target = state.questions.find((q) => q.number === questionNumber);
    if (!target) return;

    dispatch({
      type: "QUESTION_JUMP",
      questionNumber,
      section: target.section,
    });

    requestAnimationFrame(() => {
      document
        .querySelector(`[data-testid="question-${questionNumber}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  const handleConfirmSubmit = async () => {
    dispatch({ type: "SUBMIT_STARTED" });
    try {
      // Only ever sends state.answers — highlights are structurally
      // unreachable from here (PassagePanel never surfaces them upward).
      const result = await submitReadingSession(sessionId, state.answers);
      setShowSubmitModal(false);
      onSubmitted(result, state.questions);
    } catch (err) {
      dispatch({
        type: "SUBMIT_FAILED",
        error: err instanceof Error ? err.message : "Failed to submit exam.",
      });
    }
  };

  const prevForceSubmitRef = useRef(forceSubmitSignal);
  useEffect(() => {
    if (
      forceSubmitSignal !== undefined &&
      prevForceSubmitRef.current !== forceSubmitSignal
    ) {
      prevForceSubmitRef.current = forceSubmitSignal;
      handleConfirmSubmit();
    }
    // handleConfirmSubmit is intentionally not a dependency — it closes over
    // state that changes on every keystroke, and re-running this effect for
    // that would defeat the point; forceSubmitSignal is the only real
    // trigger, guarded by the ref comparison above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceSubmitSignal]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SectionTabs
        activeSection={state.activeSection}
        onSectionChange={(section) =>
          dispatch({ type: "SECTION_CHANGED", section })
        }
      />

      <div className="flex min-h-0 flex-1">
        {/* Left: passage, independently scrollable. Keyed on section so a
            new passage never inherits highlights that belong to a
            different passage's text. */}
        <div className="min-h-0 w-1/2">
          <PassagePanel
            key={state.activeSection}
            passageText={activePassage}
            passageNumber={state.activeSection}
          />
        </div>

        {/* Right: questions, independently scrollable, plus the nav sidebar. */}
        <div className="flex min-h-0 w-1/2">
          <div className="min-h-0 flex-1 space-y-8 overflow-y-auto p-8">
            {activeQuestions.map((question) => (
              <QuestionRenderer
                key={question.number}
                question={question}
                value={state.answers[String(question.number)] ?? ""}
                onChange={(value) =>
                  dispatch({
                    type: "ANSWER_CHANGED",
                    questionNumber: question.number,
                    value,
                  })
                }
              />
            ))}
          </div>

          <div className="min-h-0 w-44 shrink-0 overflow-y-auto border-l border-border bg-canvas-subtle">
            <QuestionNavSidebar
              questions={state.questions}
              answers={state.answers}
              activeQuestionNumber={state.activeQuestionNumber}
              onJump={handleJump}
            />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border bg-surface px-6 py-3">
        {state.submitError ? (
          <p className="text-xs text-danger" role="alert">{state.submitError}</p>
        ) : (
          <span
            data-testid="reading-progress"
            className="text-xs text-fg-subtle"
          >
            {formatReadingProgress(progress)}
          </span>
        )}
        <button
          type="button"
          data-testid="reading-submit-button"
          onClick={() => setShowSubmitModal(true)}
          className="rounded-full bg-brand px-4 py-1.5 text-xs font-semibold text-fg-on-brand transition hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          Submit Exam
        </button>
      </div>

      {showSubmitModal && (
        <SubmitConfirmModal
          unansweredCount={unansweredCount}
          submitting={state.submitting}
          onConfirm={handleConfirmSubmit}
          onCancel={() => setShowSubmitModal(false)}
        />
      )}
    </div>
  );
}
