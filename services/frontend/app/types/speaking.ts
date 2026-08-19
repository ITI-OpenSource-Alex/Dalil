// Mirrors the JSON shapes returned by the Speaking Service's
// /sessions* endpoints (services/speaking/internal/speaking/sessions_handler.go).

/** One dimension of the IELTS evaluation swarm's output (Fluency, Lexical, Grammar, Pronunciation). */
export interface SpeakingCriterionResult {
  criterion: string;
  /** Absent for a criterion that timed out; the swarm omits it rather than
   *  sending 0.0, which would be indistinguishable from a real score. */
  band?: number;
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

/**
 * Flat, UI-friendly band scores for the 4 IELTS speaking criteria.
 *
 * null means "this criterion produced no score" (its agent timed out or
 * errored). It is deliberately not 0: zero is a valid IELTS band, so a numeric
 * placeholder is indistinguishable from a real result (GOA-032, BUG-055).
 */
export interface SpeakingCriteriaScores {
  fluency: number | null;
  lexical: number | null;
  grammar: number | null;
  pronunciation: number | null;
}

/** The canonical shape rendered by <EvaluationBreakdown>. */
export interface SpeakingEvaluationResult {
  /** null when fewer than 3 criteria completed — see SpeakingSessionSummary. */
  overallScore: number | null;
  criteria: SpeakingCriteriaScores;
  feedback?: string;
}

/** GET /api/speaking/sessions list item. */
export interface SpeakingSessionSummary {
  id: string;
  question_prompt: string;
  question_type: string;
  /** null when fewer than 3 of the 4 criteria completed — render "not scored",
   *  never 0.0, which is a real IELTS band (GOA-032, BUG-040). */
  overall_band: number | null;
  created_at: string;
}

/** GET /api/speaking/sessions/{id} and GET /speaking/sessions/public/{token}. */
export interface SpeakingSessionDetail {
  id: string;
  question_prompt: string;
  question_type: string;
  transcript: string;
  evaluation: SpeakingDimensions;
  overall_band: number | null;
  created_at: string;
}

/** POST /sessions/{id}/share response. */
export interface CreateShareLinkResponse {
  share_token: string;
}
