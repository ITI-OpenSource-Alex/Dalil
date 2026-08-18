"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import QuestionRenderer from "@/components/reading/questions/QuestionRenderer";
import LockedAudioPlayer from "@/components/listening/LockedAudioPlayer";
import type { NormalizedReadingQuestion } from "@/app/types/reading";
import type {
  ListeningAnswers,
  ListeningSection,
  ListeningSubmitResponse,
  NormalizedListeningQuestion,
} from "@/app/types/listening";
import { submitListeningSession } from "@/lib/listening-api";
import {
  initialListeningState,
  listeningReducer,
} from "@/lib/listening-reducer";
import type { RawReadingQuestion } from "@/app/types/reading";

interface ListeningExamProps {
  sessionId: string;
  audioUrls: [string, string, string, string];
  rawQuestions: RawReadingQuestion[];
  stimulusImageUrl?: string | null;
  onSubmitted: (
    result: ListeningSubmitResponse,
    questions: NormalizedListeningQuestion[],
  ) => void;
  /** Incremented by the outer exam clock when the overall limit expires. */
  forceSubmitSignal?: number;
}

interface ListeningQuestionGroup {
  instructions: string | null;
  questions: NormalizedListeningQuestion[];
}

function groupQuestionsByInstructions(
  questions: NormalizedListeningQuestion[],
): ListeningQuestionGroup[] {
  return questions.reduce<ListeningQuestionGroup[]>((groups, question) => {
    const instructions = question.instructions?.trim() || null;
    const previous = groups.at(-1);

    if (previous?.instructions === instructions) {
      previous.questions.push(question);
      return groups;
    }

    groups.push({ instructions, questions: [question] });
    return groups;
  }, []);
}

function questionRangeLabel(questions: NormalizedListeningQuestion[]): string {
  const first = questions[0].number;
  const last = questions.at(-1)?.number ?? first;
  return first === last ? `Question ${first}` : `Questions ${first}–${last}`;
}

function formatTime(totalSeconds: number | null): string {
  const safeSeconds = totalSeconds ?? 0;
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function ListeningExam({
  sessionId,
  audioUrls,
  rawQuestions,
  stimulusImageUrl = null,
  onSubmitted,
  forceSubmitSignal = 0,
}: ListeningExamProps) {
  const [state, dispatch] = useReducer(
    listeningReducer,
    rawQuestions,
    initialListeningState,
  );
  const [scratchPad, setScratchPad] = useState("");
  const lastForcedSubmitSignal = useRef(0);

  const activeQuestions = useMemo(
    () =>
      state.questions.filter(
        (question) => question.section === state.activeSection,
      ),
    [state.activeSection, state.questions],
  );

  const mapSection = useMemo(() => {
    const mapQuestion = rawQuestions.find((question) =>
      question.question_type.toLowerCase().includes("map labelling"),
    );
    if (!mapQuestion) return null;
    return (mapQuestion.section_number ??
      Math.ceil(mapQuestion.number / 10)) as ListeningSection;
  }, [rawQuestions]);

  const visibleQuestions =
    state.phase === "answer_transfer" || state.phase === "submitting"
      ? state.questions
      : activeQuestions;

  // The 30-second gap only runs after the candidate explicitly clicks Next.
  useEffect(() => {
    if (state.phase !== "silence_gap") return;

    const interval = window.setInterval(() => {
      dispatch({ type: "SILENCE_TICK" });
    }, 1000);

    return () => window.clearInterval(interval);
  }, [state.phase]);

  // The transfer timer begins only after Section 4 ends.
  useEffect(() => {
    if (
      state.phase !== "answer_transfer" ||
      state.transferSecondsRemaining === 0
    ) {
      return;
    }

    const interval = window.setInterval(() => {
      dispatch({ type: "TRANSFER_TICK" });
    }, 1000);

    return () => window.clearInterval(interval);
  }, [state.phase, state.transferSecondsRemaining]);

  const handleSubmit = useCallback(
    async (forced = false) => {
      if ((!forced && state.phase !== "answer_transfer") || state.submitting) {
        return;
      }

      dispatch({ type: "SUBMIT_STARTED" });

      try {
        // Scratch-pad content is intentionally not part of this call.
        const result = await submitListeningSession(
          sessionId,
          state.answers as ListeningAnswers,
        );

        onSubmitted(result, state.questions);
      } catch (error) {
        dispatch({
          type: "SUBMIT_FAILED",
          error:
            error instanceof Error
              ? error.message
              : "Unable to submit listening exam.",
        });
      }
    },
    [
      onSubmitted,
      sessionId,
      state.answers,
      state.phase,
      state.questions,
      state.submitting,
    ],
  );

  // IELTS answer-transfer time is a hard deadline. Reaching zero must submit
  // the answers already saved in reducer state; disabling the button alone
  // would strand the attempt in an impossible-to-complete state.
  useEffect(() => {
    if (
      state.phase === "answer_transfer" &&
      state.transferSecondsRemaining === 0 &&
      !state.submitting
    ) {
      void handleSubmit(false);
    }
  }, [
    handleSubmit,
    state.phase,
    state.submitting,
    state.transferSecondsRemaining,
  ]);

  useEffect(() => {
    if (
      forceSubmitSignal > lastForcedSubmitSignal.current &&
      !state.submitting
    ) {
      lastForcedSubmitSignal.current = forceSubmitSignal;
      void handleSubmit(true);
    }
  }, [forceSubmitSignal, handleSubmit, state.submitting]);

  const handleQuestionChange = (questionNumber: number, value: string) => {
    dispatch({
      type: "ANSWER_CHANGED",
      questionNumber,
      value,
    });
  };

  const isListening = state.phase === "section_playing";
  const showAudio =
    state.phase !== "answer_transfer" && state.phase !== "submitting";
  const showStimulus =
    stimulusImageUrl !== null &&
    mapSection !== null &&
    (state.activeSection === mapSection ||
      state.phase === "answer_transfer" ||
      state.phase === "submitting");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-gray-400">
              Listening Exam
            </p>
            <h2 className="font-serif text-xl text-gray-900">
              {state.phase === "answer_transfer"
                ? "Answer transfer period"
                : `Section ${state.activeSection} of 4`}
            </h2>
          </div>

          {state.phase === "silence_gap" && (
            <div
              data-testid="silence-countdown"
              className="rounded-full bg-amber-50 px-4 py-2 font-mono text-sm font-semibold text-amber-800"
            >
              Next section begins in {formatTime(state.silenceSecondsRemaining)}
            </div>
          )}

          {state.phase === "answer_transfer" && (
            <div
              data-testid="answer-transfer-countdown"
              className="rounded-full bg-emerald-50 px-4 py-2 font-mono text-sm font-semibold text-emerald-800"
            >
              Transfer time: {formatTime(state.transferSecondsRemaining)}
            </div>
          )}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-2">
        <section className="min-h-0 overflow-y-auto border-r border-gray-200 bg-gray-50 p-6">
          {showAudio && (
            <LockedAudioPlayer
              key={state.activeSection}
              src={audioUrls[state.activeSection - 1]}
              autoPlay={isListening}
              onComplete={() => dispatch({ type: "AUDIO_ENDED" })}
            />
          )}

          {showStimulus && (
            <figure className="mt-6 overflow-hidden rounded-2xl border border-gray-200 bg-white p-4">
              <figcaption className="mb-3 text-sm font-bold text-gray-900">
                Map for Section {mapSection}
              </figcaption>
              <img
                src={stimulusImageUrl}
                alt={`Map for Section ${mapSection} questions`}
                className="h-auto w-full rounded-xl object-contain"
              />
            </figure>
          )}

          {state.phase === "section_complete" && (
            <button
              type="button"
              data-testid="next-section-button"
              onClick={() => dispatch({ type: "NEXT_SECTION_CLICKED" })}
              className="mt-5 rounded-full bg-[#0d4d3a] px-4 py-2 text-xs font-semibold text-white"
            >
              Next Section
            </button>
          )}

          <div className="mt-6 rounded-2xl border border-gray-200 bg-white p-5">
            <label
              htmlFor="listening-scratch-pad"
              className="block text-sm font-bold text-gray-900"
            >
              Scratch pad
            </label>
            <p className="mt-1 text-xs text-gray-500">
              Notes are private to this attempt and are not submitted.
            </p>
            <textarea
              id="listening-scratch-pad"
              data-testid="listening-scratch-pad"
              value={scratchPad}
              onChange={(event) => setScratchPad(event.target.value)}
              className="mt-4 min-h-48 w-full resize-y rounded-xl border border-gray-200 p-3 text-sm outline-none focus:border-emerald-600"
              placeholder="Type notes here…"
            />
          </div>
        </section>

        <section className="min-h-0 overflow-y-auto bg-white p-6">
          {(state.phase === "answer_transfer" ||
            state.phase === "submitting") && (
            <nav
              className="mb-6 flex flex-wrap gap-2"
              aria-label="Listening sections"
            >
              {([1, 2, 3, 4] as ListeningSection[]).map((section) => (
                <a
                  key={section}
                  href={`#listening-section-${section}`}
                  className="rounded-full border border-gray-200 px-3 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-50"
                >
                  Section {section}
                </a>
              ))}
            </nav>
          )}

          {([1, 2, 3, 4] as ListeningSection[]).map((section) => {
            const questions =
              state.phase === "answer_transfer" || state.phase === "submitting"
                ? state.questions.filter(
                    (question) => question.section === section,
                  )
                : section === state.activeSection
                  ? visibleQuestions
                  : [];

            if (!questions.length) return null;

            const questionGroups = groupQuestionsByInstructions(questions);

            return (
              <div
                key={section}
                id={`listening-section-${section}`}
                className="mb-10 space-y-8"
              >
                {(state.phase === "answer_transfer" ||
                  state.phase === "submitting") && (
                  <h3 className="border-b border-gray-100 pb-3 font-serif text-xl">
                    Section {section}
                  </h3>
                )}

                {questionGroups.map((group) => {
                  const firstNumber = group.questions[0].number;

                  return (
                    <div key={firstNumber} className="space-y-8">
                      {group.instructions && (
                        <div
                          role="note"
                          data-testid={`listening-instructions-${firstNumber}`}
                          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3"
                        >
                          <p className="text-xs font-bold uppercase tracking-wide text-emerald-800">
                            {questionRangeLabel(group.questions)}
                          </p>
                          <p className="mt-1 text-sm font-semibold text-gray-900">
                            {group.instructions}
                          </p>
                        </div>
                      )}

                      {group.questions.map((question) => (
                        <QuestionRenderer
                          key={question.number}
                          // The group heading renders shared instructions once,
                          // rather than repeating them beneath every question.
                          question={
                            {
                              ...question,
                              instructions: null,
                            } as NormalizedReadingQuestion
                          }
                          value={state.answers[String(question.number)] ?? ""}
                          onChange={(value) =>
                            handleQuestionChange(question.number, value)
                          }
                        />
                      ))}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </section>
      </div>

      <footer className="flex items-center justify-between border-t border-gray-200 bg-white px-6 py-3">
        <span className="text-xs text-gray-500">
          {
            Object.values(state.answers).filter((answer) => answer.trim())
              .length
          }{" "}
          of {state.questions.length} answered
        </span>

        {state.submitError && (
          <span className="text-xs text-red-600">{state.submitError}</span>
        )}

        {state.phase === "answer_transfer" && (
          <button
            type="button"
            data-testid="listening-submit-button"
            disabled={state.submitting || state.transferSecondsRemaining === 0}
            onClick={() => void handleSubmit(false)}
            className="rounded-full bg-[#0d4d3a] px-5 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {state.submitting ? "Submitting…" : "Submit answers"}
          </button>
        )}
      </footer>
    </div>
  );
}
