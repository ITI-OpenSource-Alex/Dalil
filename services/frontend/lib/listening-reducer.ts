import type {
  ListeningExamState,
  ListeningSection,
} from "@/app/types/listening";
import { normalizeListeningQuestions } from "@/lib/listening-api";
import type { RawReadingQuestion } from "@/app/types/reading";

export const SILENCE_GAP_SECONDS = 30;
export const ANSWER_TRANSFER_SECONDS = 10 * 60;

export type ListeningAction =
  | { type: "ANSWER_CHANGED"; questionNumber: number; value: string }
  | { type: "AUDIO_ENDED" }
  | { type: "NEXT_SECTION_CLICKED" }
  | { type: "SILENCE_TICK" }
  | { type: "TRANSFER_TICK" }
  | { type: "SUBMIT_STARTED" }
  | { type: "SUBMIT_FAILED"; error: string };

export function initialListeningState(
  rawQuestions: RawReadingQuestion[],
): ListeningExamState {
  return {
    phase: "section_playing",
    activeSection: 1,
    questions: normalizeListeningQuestions(rawQuestions),
    answers: {},
    silenceSecondsRemaining: null,
    transferSecondsRemaining: null,
    submitting: false,
    submitError: null,
  };
}

export function listeningReducer(
  state: ListeningExamState,
  action: ListeningAction,
): ListeningExamState {
  switch (action.type) {
    case "ANSWER_CHANGED":
      return {
        ...state,
        answers: {
          ...state.answers,
          [String(action.questionNumber)]: action.value,
        },
      };

    case "AUDIO_ENDED":
      // Audio finishing after a section is the only way to expose Next.
      if (state.activeSection === 4) {
        return {
          ...state,
          phase: "answer_transfer",
          transferSecondsRemaining: ANSWER_TRANSFER_SECONDS,
        };
      }

      return {
        ...state,
        phase: "section_complete",
      };

    case "NEXT_SECTION_CLICKED":
      if (state.phase !== "section_complete") return state;

      return {
        ...state,
        phase: "silence_gap",
        silenceSecondsRemaining: SILENCE_GAP_SECONDS,
      };

    case "SILENCE_TICK": {
      // A tick only means anything during the gap.
      //
      // Without this guard the timer advanced the exam from any phase: outside
      // the gap `silenceSecondsRemaining` is null, so `max(0, 0 - 1)` is 0 and
      // control fell straight through to the advance branch. A stray tick in
      // `section_complete` skipped the section without the required click, and
      // ticks arriving after the gap had already elapsed advanced again --
      // walking the candidate past sections they never heard.
      //
      // One-pass integrity is the property that makes a Listening score mean
      // anything, and it cannot depend on no timer ever firing at the wrong
      // moment. A reducer has to reject actions that are invalid for its
      // current phase rather than assume the caller only sends valid ones.
      if (state.phase !== "silence_gap") {
        return state;
      }

      const remaining = Math.max(0, (state.silenceSecondsRemaining ?? 0) - 1);

      if (remaining > 0) {
        return { ...state, silenceSecondsRemaining: remaining };
      }

      return {
        ...state,
        activeSection: (state.activeSection + 1) as ListeningSection,
        phase: "section_playing",
        // Rests at 0 rather than null. The gap did elapse, and 0 records that;
        // null would read as "no gap has run", which is what the UI shows
        // before the first section ends.
        silenceSecondsRemaining: 0,
      };
    }

    case "TRANSFER_TICK": {
      const remaining = Math.max(0, (state.transferSecondsRemaining ?? 0) - 1);

      return {
        ...state,
        transferSecondsRemaining: remaining,
      };
    }

    case "SUBMIT_STARTED":
      return {
        ...state,
        phase: "submitting",
        submitting: true,
        submitError: null,
      };

    case "SUBMIT_FAILED":
      return {
        ...state,
        phase: "answer_transfer",
        submitting: false,
        submitError: action.error,
      };
  }
}
