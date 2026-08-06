import { throwForResponse } from "@/lib/subscription";

// Reached through the Gateway's POST /api/opportunities/query
// (services/gateway/handlers/opportunities.go), which builds RAG's request
// body itself from the JWT — no user id is sent from the browser, by design.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api`;

/**
 * One ranked programme, exactly as RAG's `match_programs` emits it
 * (services/rag/app/services/scoring.py).
 *
 * `deadline` is nullable: the query selects it straight out of
 * program_requirements, where it is optional, and returns None for a
 * programme with no published date. The chat path's copy of this type
 * declared it as a plain `string`, which is why an undated programme rendered
 * "Deadline: null".
 *
 * `result.score` is 0-100, not 0-1.
 */
export interface MatchedProgram {
  programId: string;
  programName: string;
  university: string;
  country: string;
  deadline: string | null;
  result: {
    score: number;
    blocked_by: string | null;
    /**
     * Per-dimension shortfalls, keyed by dimension. Values are free-form:
     * a human-readable string for the gate that blocked, or (for the
     * "financial" key) an array of structured visa-finance items.
     */
    gap_report?: Record<string, unknown>;
  };
}

export interface MatchResponse {
  programs: MatchedProgram[];
}

/**
 * POST /api/opportunities/query.
 *
 * RAG answers 425 while the user's profile has not yet replicated into its
 * own store — a real, transient state right after onboarding, and one worth
 * distinguishing from "no matches" because the fix is to wait rather than to
 * change your profile.
 */
export class ProfileNotReadyError extends Error {
  constructor() {
    super("Your profile is still syncing.");
    this.name = "ProfileNotReadyError";
  }
}

/**
 * The Gateway's hourly AI quota for this route
 * (middleware.AIRateLimiter, "opportunity_search", 20/hour). It answers 429 with
 * a Retry-After header and names the remaining wait in its message.
 *
 * Distinguished from a generic failure because it is neither a fault nor
 * something retrying now can fix: the honest answer is how long to wait. Folding
 * it into "we couldn't reach programme matching" sent a user hunting a dead
 * backend when the backend was healthy and had simply said "not this often".
 */
export class RateLimitedError extends Error {
  readonly retryAfterSeconds: number | null;

  constructor(retryAfterSeconds: number | null) {
    super("You have reached this hour's programme matching limit.");
    this.name = "RateLimitedError";
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** "12 minutes" / "45 seconds" — for telling the user when to come back. */
export function formatRetryAfter(seconds: number | null): string | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds <= 0) return null;
  if (seconds < 90) return `${Math.ceil(seconds)} seconds`;
  return `${Math.ceil(seconds / 60)} minutes`;
}

export async function searchOpportunities(
  signal?: AbortSignal,
): Promise<MatchedProgram[]> {
  const response = await fetch(`${API_BASE}/opportunities/query`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    // The Gateway ignores the body entirely (it constructs RAG's payload from
    // the token), but sending {} keeps the request a well-formed JSON POST.
    body: "{}",
    signal,
  });

  if (response.status === 425) throw new ProfileNotReadyError();
  if (response.status === 429) {
    // Retry-After is seconds here (the Gateway writes an integer, never a date).
    const header = response.headers.get("Retry-After");
    const parsed = header === null ? NaN : Number.parseInt(header, 10);
    throw new RateLimitedError(Number.isFinite(parsed) ? parsed : null);
  }
  if (!response.ok) await throwForResponse(response);

  const data = (await response.json()) as MatchResponse;
  return Array.isArray(data?.programs) ? data.programs : [];
}

/* ------------------------------------------------------------------ *
 * Presentation helpers, kept next to the type they describe so the page
 * and the chat cards cannot disagree about what a score means.
 * ------------------------------------------------------------------ */

export type MatchTone = "strong" | "possible" | "stretch" | "blocked";

export function matchTone(program: MatchedProgram): MatchTone {
  if (program.result.blocked_by) return "blocked";
  if (program.result.score >= 65) return "strong";
  if (program.result.score >= 45) return "possible";
  return "stretch";
}

export const MATCH_TONE_LABEL: Record<MatchTone, string> = {
  strong: "Strong match",
  possible: "Possible match",
  stretch: "Stretch",
  blocked: "Requirement not met",
};

/**
 * Turns RAG's `blocked_by` gate id into something a candidate can act on.
 * The raw values are internal identifiers ("ielts", "ects"); showing them was
 * the same class of leak as the chat's "Route: RAG" badge.
 */
export function blockedReason(gate: string | null): string | null {
  if (!gate) return null;
  const reasons: Record<string, string> = {
    ielts: "Your IELTS band is below this programme's minimum.",
    gpa: "Your GPA is below this programme's minimum.",
    ects: "You have fewer ECTS credits than this programme requires.",
    degree_level: "This programme expects a different degree level.",
    citizenship: "This programme is restricted to certain citizenships.",
    work_experience: "This programme requires more work experience.",
  };
  return reasons[gate] ?? "You don't meet one of this programme's requirements yet.";
}

/** "15 Oct 2026", or null when the programme publishes no deadline. */
export function formatDeadline(deadline: string | null): string | null {
  if (!deadline) return null;
  const date = new Date(deadline);
  if (Number.isNaN(date.getTime())) return deadline;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Whole days until the deadline; negative once it has passed. */
export function daysUntil(deadline: string | null): number | null {
  if (!deadline) return null;
  const date = new Date(deadline);
  if (Number.isNaN(date.getTime())) return null;
  const MS_PER_DAY = 24 * 60 * 60 * 1000;
  return Math.ceil((date.getTime() - Date.now()) / MS_PER_DAY);
}
