// Reading-specific types (GOA-055).
//
// The backend's raw question shape (confirmed against
// services/exam/app/ingestion/parser.py and real parsed fixtures) has no
// `id` field — only a numeric `number` — and no structured options list for
// Multiple Choice / Matching. See normalizeReadingQuestions.ts for how
// RawReadingQuestion becomes a NormalizedReadingQuestion the UI can render.

/** The 5 question-type categories GOA-055's renderers support. */
export type ReadingUiType =
  | "multiple_choice"
  | "matching"
  | "true_false_not_given"
  | "fill_in_blank"
  | "short_answer";

/** Verbatim shape of one question object as returned by the exam service. */
export interface RawReadingQuestion {
  number: number;
  prompt: string;
  question_type: string;
  instructions?: string | null;
  passage_number: number | null;
  section_number?: number | null;
}

/** A question after normalization: bucketed into a UI type, with any
 * derived data (e.g. parsed MC/Matching options) attached. */
export interface NormalizedReadingQuestion {
  number: number;
  prompt: string;
  /** Original backend value, kept for debugging/telemetry — never used for rendering decisions. */
  rawQuestionType: string;
  uiType: ReadingUiType;
  instructions?: string | null;
  passageNumber: number | null;
  section: 1 | 2 | 3;
  /** Only populated for multiple_choice / matching — see normalizeReadingQuestions.ts. */
  options?: string[];
  /** The prompt text with any parsed option lines removed, so a renderer
   * that already lists `options` as its own controls doesn't also repeat
   * them verbatim inside the prompt. Falls back to the full `prompt` when
   * no options were parsed. */
  promptStem: string;
}

export interface ReadingStartResponse {
  session_id: string;
  passages: string[];
  questions: RawReadingQuestion[];
  time_limit_seconds: number;
}

export interface ReadingQuestionResult {
  submitted_answer: string;
  correct_answer: string;
  is_correct: boolean;
}

export interface ReadingSectionBreakdown {
  correct: number;
  total: number;
}

export interface ReadingSubmitResponse {
  raw_score: number;
  band_score: number;
  per_question_result: Record<string, ReadingQuestionResult>;
  section_breakdown: Record<string, ReadingSectionBreakdown>;
}

/** Flat map of question number (as string) -> submitted answer, matching
 * ReadingSubmitRequest.answers on the backend exactly. */
export type ReadingAnswers = Record<string, string>;
