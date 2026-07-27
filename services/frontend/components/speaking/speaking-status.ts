/**
 * Single source of truth for how each speaking-session state is presented.
 *
 * The status chip, the microphone control and the screen-reader announcement
 * all read from here so a new state can never be styled three different ways
 * (or, worse, be added to one surface and forgotten on the others).
 */
export type SpeakingState =
  | "idle"
  | "connecting"
  | "listening"
  | "transcribing"
  | "evaluating"
  | "done"
  | "error";

export interface SpeakingStateMeta {
  /** Human-facing label. Deliberately product language, not internal state names. */
  label: string;
  /** Chip text colour. */
  text: string;
  /** Chip background. */
  bg: string;
  /** Chip border. */
  border: string;
  /** Indicator dot / icon colour. */
  accent: string;
  /** Whether this state is mid-flight and should read as "busy". */
  busy: boolean;
}

export const SPEAKING_STATE_META: Record<SpeakingState, SpeakingStateMeta> = {
  idle: {
    label: "Ready",
    text: "text-[#526053]",
    bg: "bg-[#F4F6F3]",
    border: "border-[#E3E8E1]",
    accent: "bg-[#9AA79B]",
    busy: false,
  },
  connecting: {
    label: "Connecting",
    text: "text-amber-700",
    bg: "bg-amber-50",
    border: "border-amber-200/70",
    accent: "bg-amber-500",
    busy: true,
  },
  listening: {
    label: "Listening",
    text: "text-emerald-700",
    bg: "bg-emerald-50",
    border: "border-emerald-200/70",
    accent: "bg-emerald-500",
    busy: false,
  },
  transcribing: {
    label: "Processing",
    text: "text-sky-700",
    bg: "bg-sky-50",
    border: "border-sky-200/70",
    accent: "bg-sky-500",
    busy: true,
  },
  evaluating: {
    label: "Evaluating",
    text: "text-indigo-700",
    bg: "bg-indigo-50",
    border: "border-indigo-200/70",
    accent: "bg-indigo-500",
    busy: true,
  },
  done: {
    label: "Completed",
    text: "text-emerald-700",
    bg: "bg-emerald-50",
    border: "border-emerald-200/70",
    accent: "bg-emerald-500",
    busy: false,
  },
  error: {
    label: "Error",
    text: "text-red-700",
    bg: "bg-red-50",
    border: "border-red-200/70",
    accent: "bg-red-500",
    busy: false,
  },
};

/**
 * Which states offer "start" versus "stop". Kept here so the control and the
 * helper hint below can never disagree about which button is on screen.
 *
 * NOTE: this mirrors the pre-existing behaviour exactly and is intentionally
 * not "improved" — switching which callback a state fires would be a
 * behavioural change, not a visual one.
 */
export function isStartState(state: SpeakingState): boolean {
  return state === "idle" || state === "error" || state === "connecting";
}

/** Short helper text shown under the microphone control. */
export function speakingHint(state: SpeakingState): string {
  switch (state) {
    case "idle":
      return "Tap the microphone to begin";
    case "connecting":
      return "Connecting to the speaking service…";
    case "listening":
      return "Listening — tap to finish";
    case "transcribing":
      return "Transcribing your answer…";
    case "evaluating":
      return "Scoring against IELTS criteria…";
    case "done":
      return "Session complete";
    case "error":
      return "Something went wrong";
  }
}
