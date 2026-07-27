// Mirrors the JSON shapes returned by the Speaking Service's
// /sessions* endpoints (services/speaking/internal/speaking/sessions_handler.go).

/** One dimension of the IELTS evaluation swarm's output (Fluency, Lexical, Grammar, Pronunciation). */
export interface SpeakingCriterionResult {
  criterion: string;
  band: number;
  feedback: string;
  examples?: string[];
  timed_out?: boolean;
}

/**
 * The raw `evaluation` JSONB blob, keyed by the swarm's long-form dimension
 * names (e.g. "Fluency and Coherence") — NOT the short "fluency" style keys
 * used elsewhere in the UI. Use extractCriteriaScores() from
 * lib/speaking-format.ts to convert this into SpeakingCriteriaScores.
 */
export type SpeakingDimensions = Record<string, SpeakingCriterionResult>;

/** Flat, UI-friendly band scores for the 4 IELTS speaking criteria. */
export interface SpeakingCriteriaScores {
  fluency: number;
  lexical: number;
  grammar: number;
  pronunciation: number;
}

/** The canonical shape rendered by <EvaluationBreakdown>. */
export interface SpeakingEvaluationResult {
  overallScore: number;
  criteria: SpeakingCriteriaScores;
  feedback?: string;
}

/** GET /sessions?userId=... list item. */
export interface SpeakingSessionSummary {
  id: string;
  question_prompt: string;
  question_type: string;
  overall_band: number;
  created_at: string;
}

/** GET /sessions/{id} and GET /sessions/public/{token} response. */
export interface SpeakingSessionDetail {
  id: string;
  question_prompt: string;
  question_type: string;
  transcript: string;
  evaluation: SpeakingDimensions;
  overall_band: number;
  created_at: string;
}

/** POST /sessions/{id}/share response. */
export interface CreateShareLinkResponse {
  share_token: string;
}
