import type {
  NormalizedReadingQuestion,
  RawReadingQuestion,
  ReadingAnswers,
  ReadingQuestionResult,
  ReadingSectionBreakdown,
} from "@/app/types/reading";

export type ListeningSection = 1 | 2 | 3 | 4;

export type ListeningPhase =
  | "section_playing"
  | "section_complete"
  | "silence_gap"
  | "answer_transfer"
  | "submitting"
  | "submit_error";

export interface ListeningStartResponse {
  session_id: string;
  audio_urls: [string, string, string, string];
  questions: RawReadingQuestion[];
  time_limit_seconds: number;
  audio_url_expiry_seconds: number;
}

export interface NormalizedListeningQuestion extends Omit<
  NormalizedReadingQuestion,
  "section"
> {
  section: ListeningSection;
}

export type ListeningAnswers = ReadingAnswers;

export interface ListeningQuestionResult extends ReadingQuestionResult {}

export interface ListeningSubmitResponse {
  raw_score: number;
  band_score: number;
  per_question_result: Record<string, ListeningQuestionResult>;
  section_breakdown: Record<string, ReadingSectionBreakdown>;
}

export interface ListeningExamState {
  phase: ListeningPhase;
  activeSection: ListeningSection;
  questions: NormalizedListeningQuestion[];
  answers: ListeningAnswers;

  // Decreases from 30 to 0 between sections.
  silenceSecondsRemaining: number | null;

  // Decreases from 600 to 0 after section 4 audio ends.
  transferSecondsRemaining: number | null;

  submitting: boolean;
  submitError: string | null;
}
