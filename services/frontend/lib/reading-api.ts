import type { ReadingAnswers, ReadingSubmitResponse } from "@/app/types/reading";
import type { ExamSessionResponse } from "@/lib/exam-api";

// Reading-specific client for the /exam/reading/* endpoint.
//
// Why this exists alongside lib/exam-api.ts rather than extending it: the
// generic PUT /sessions/:id/submit (services/exam/app/services/
// session_service.py:submit_session) calls the generic grade(), whose
// return value is only {session_id, status, raw_score, band_score} — no
// per_question_result, no section_breakdown. That data only exists behind
// the separate PUT /exam/reading/:id/submit endpoint
// (submit_reading_session -> grade_reading). Session *creation* and
// *fetching* still go through the existing generic /sessions endpoints
// (lib/exam-api.ts's createSession/getSession) — a session created there is
// fully compatible with this submit call, since both paths write to the
// same sessions/questions tables and submit_reading_session only needs a
// valid session_id. Only submission needs this separate client.
//
// Reached through the Gateway, not directly on :8085 — same reason as
// exam-api.ts (BUG-046): calling the service directly meant shipping
// INTERNAL_API_KEY to the browser in a NEXT_PUBLIC_ variable. The Gateway
// proxies this one Reading-specific route (services/gateway/handlers/
// exam.go's SubmitReadingSession) the same way it does the generic session
// routes, holding the key server-side and requiring the same JWT auth.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/exam`;

const headers = {
  "Content-Type": "application/json",
};

const fetchOptions: RequestInit = { credentials: "include" };

export async function submitReadingSession(
  sessionId: string,
  answers: ReadingAnswers,
): Promise<ReadingSubmitResponse> {
  const response = await fetch(`${API_BASE}/reading/${sessionId}/submit`, {
    ...fetchOptions,
    method: "PUT",
    headers,
    body: JSON.stringify({ answers }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

// GET /exam/reading/start pre-splits passage_text on "---" server-side
// (session_service.py:258) but only for a *newly created* session — there is
// no GET-by-id endpoint on that router to re-fetch an existing session in
// the same shape. Sessions are instead fetched via the generic
// GET /sessions/:id (lib/exam-api.ts's getSession), whose _public_question
// returns the same passage_text raw and unsplit. This replicates that exact
// split so a session fetched either way renders identically.
export function splitPassages(passageText: string | null | undefined): string[] {
  if (!passageText) return [];
  return passageText
    .split("---")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

// The generic session response wraps a single question record whose own
// `.questions` field is the actual per-question array (see
// session_service.py's _question_list / _public_question). This just gives
// that extraction a name at the call site rather than repeating the
// `session.questions[0]?.questions` reach-through inline.
export function extractRawQuestions(
  session: ExamSessionResponse,
): Record<string, unknown>[] {
  return session.questions[0]?.questions ?? [];
}
