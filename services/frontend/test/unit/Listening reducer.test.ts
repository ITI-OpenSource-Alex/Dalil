import { describe, it, expect } from "vitest";
import {
  initialListeningState,
  listeningReducer,
} from "@/lib/listening-reducer";
import type { RawReadingQuestion } from "@/app/types/reading";

// NOTE ON ASSUMPTIONS: lib/listening-reducer.ts itself wasn't available to
// read directly, so these tests are written against the contract implied by
// components/listening/ListeningExam.tsx and its comments:
//   - phases: "section_playing" -> "section_complete" (on AUDIO_ENDED, for
//     sections 1-3) -> "silence_gap" (on NEXT_SECTION_CLICKED, 30s) ->
//     "section_playing" for the next section (when silenceSecondsRemaining
//     hits 0)
//   - section 4's AUDIO_ENDED skips section_complete/silence_gap entirely
//     and goes straight to "answer_transfer" (see ListeningExam's comment:
//     "The transfer timer begins only after Section 4 ends")
//   - "submitting" is a phase, but `submitting`/`submitError` are also
//     tracked as separate fields consumed directly by ListeningExam
// If the real reducer's constants (30s gap, transfer window length) or
// field names differ, update SILENCE_GAP_SECONDS below and the assertions
// that reference it accordingly.
const SILENCE_GAP_SECONDS = 30;

function makeRawQuestions(): RawReadingQuestion[] {
  return [1, 2, 3, 4].map((section) => ({
    number: section,
    section_number: section,
    type: "sentence_completion",
    prompt: `Question ${section}`,
    options: null,
    correct_answer: "answer",
  })) as unknown as RawReadingQuestion[];
}

function advanceThroughGap(state: ReturnType<typeof initialListeningState>) {
  let next = state;
  for (let i = 0; i < SILENCE_GAP_SECONDS; i++) {
    next = listeningReducer(next, { type: "SILENCE_TICK" });
  }
  return next;
}

describe("listeningReducer", () => {
  it("starts on section 1, playing", () => {
    const state = initialListeningState(makeRawQuestions());
    expect(state.activeSection).toBe(1);
    expect(state.phase).toBe("section_playing");
  });

  it("does not auto-advance the section when audio ends — it waits for an explicit click", () => {
    let state = initialListeningState(makeRawQuestions());
    state = listeningReducer(state, { type: "AUDIO_ENDED" });

    expect(state.phase).toBe("section_complete");
    expect(state.activeSection).toBe(1);

    // Ticking (or doing nothing) must not move the section forward on its
    // own; only NEXT_SECTION_CLICKED does that.
    const ticked = listeningReducer(state, { type: "SILENCE_TICK" });
    expect(ticked.activeSection).toBe(1);
    expect(ticked.phase).toBe("section_complete");
  });

  it("advances sections 1→2→3→4 in strict order, each gated by a click and a 30s gap", () => {
    let state = initialListeningState(makeRawQuestions());

    for (const expectedNext of [2, 3, 4]) {
      state = listeningReducer(state, { type: "AUDIO_ENDED" });
      expect(state.phase).toBe("section_complete");

      state = listeningReducer(state, { type: "NEXT_SECTION_CLICKED" });
      expect(state.phase).toBe("silence_gap");
      expect(state.silenceSecondsRemaining).toBe(SILENCE_GAP_SECONDS);
      // Still reporting the section that just finished until the gap
      // actually elapses.
      expect(state.activeSection).toBe(expectedNext - 1);

      state = advanceThroughGap(state);

      expect(state.silenceSecondsRemaining).toBe(0);
      expect(state.phase).toBe("section_playing");
      expect(state.activeSection).toBe(expectedNext);
    }
  });

  it("never lets the silence gap go negative if ticked past zero", () => {
    let state = initialListeningState(makeRawQuestions());
    state = listeningReducer(state, { type: "AUDIO_ENDED" });
    state = listeningReducer(state, { type: "NEXT_SECTION_CLICKED" });

    for (let i = 0; i < SILENCE_GAP_SECONDS + 5; i++) {
      state = listeningReducer(state, { type: "SILENCE_TICK" });
    }

    expect(state.silenceSecondsRemaining).toBe(0);
  });

  it("starts the answer-transfer period immediately when section 4 ends — no gap, no Next-Section step", () => {
    let state = initialListeningState(makeRawQuestions());

    // Walk through sections 1-3.
    for (let i = 0; i < 3; i++) {
      state = listeningReducer(state, { type: "AUDIO_ENDED" });
      state = listeningReducer(state, { type: "NEXT_SECTION_CLICKED" });
      state = advanceThroughGap(state);
    }
    expect(state.activeSection).toBe(4);
    expect(state.phase).toBe("section_playing");

    state = listeningReducer(state, { type: "AUDIO_ENDED" });

    expect(state.phase).toBe("answer_transfer");
    expect(state.activeSection).toBe(4);
    expect(state.transferSecondsRemaining).toBeGreaterThan(0);
  });

  it("counts down the transfer window on each tick and floors at zero", () => {
    let state = initialListeningState(makeRawQuestions());
    for (let i = 0; i < 3; i++) {
      state = listeningReducer(state, { type: "AUDIO_ENDED" });
      state = listeningReducer(state, { type: "NEXT_SECTION_CLICKED" });
      state = advanceThroughGap(state);
    }
    state = listeningReducer(state, { type: "AUDIO_ENDED" });
    expect(state.phase).toBe("answer_transfer");

    expect(state.transferSecondsRemaining).not.toBeNull();
    const start = state.transferSecondsRemaining!;
    state = listeningReducer(state, { type: "TRANSFER_TICK" });
    expect(state.transferSecondsRemaining).toBe(start - 1);

    for (let i = 0; i < start + 5; i++) {
      state = listeningReducer(state, { type: "TRANSFER_TICK" });
    }
    expect(state.transferSecondsRemaining).toBe(0);
    // Running out the transfer window on its own should not silently
    // discard the candidate's answers or change the phase away from
    // answer_transfer (the shell/ListeningExam UI, not the reducer, is
    // responsible for disabling submission once it hits zero).
    expect(state.phase).toBe("answer_transfer");
  });

  it("records an answer by question number without disturbing phase or section", () => {
    let state = initialListeningState(makeRawQuestions());
    state = listeningReducer(state, {
      type: "ANSWER_CHANGED",
      questionNumber: 1,
      value: "42",
    });

    expect(state.answers["1"]).toBe("42");
    expect(state.phase).toBe("section_playing");
    expect(state.activeSection).toBe(1);
  });

  it("preserves earlier answers when later ones are recorded", () => {
    let state = initialListeningState(makeRawQuestions());
    state = listeningReducer(state, {
      type: "ANSWER_CHANGED",
      questionNumber: 1,
      value: "first",
    });
    state = listeningReducer(state, {
      type: "ANSWER_CHANGED",
      questionNumber: 2,
      value: "second",
    });

    expect(state.answers["1"]).toBe("first");
    expect(state.answers["2"]).toBe("second");
  });

  it("tracks the submit lifecycle via SUBMIT_STARTED and SUBMIT_FAILED", () => {
    let state = initialListeningState(makeRawQuestions());
    state = { ...state, phase: "answer_transfer" as const };

    state = listeningReducer(state, { type: "SUBMIT_STARTED" });
    expect(state.submitting).toBe(true);
    expect(state.submitError).toBeFalsy();

    state = listeningReducer(state, {
      type: "SUBMIT_FAILED",
      error: "network error",
    });
    expect(state.submitting).toBe(false);
    expect(state.submitError).toBe("network error");
  });
});
