import {
  CreateShareLinkResponse,
  SpeakingSessionDetail,
  SpeakingSessionSummary,
} from "@/app/types/speaking";

// The speaking service is reached directly from the browser, the same way
// speaking-websocket.ts connects straight to its /ws endpoint — there's no
// gateway route for it (see the Phase 0 report for why).
const API_BASE =
  process.env.NEXT_PUBLIC_SPEAKING_API_URL ?? "http://localhost:8082";

async function parseJSONOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(
      message || `Request failed with status ${response.status}`,
    );
  }
  return response.json();
}

/** GET /sessions?userId=... — a user's speaking history, most recent first. */
export async function listSpeakingSessions(
  userId: string,
): Promise<SpeakingSessionSummary[]> {
  const response = await fetch(
    `${API_BASE}/sessions?userId=${encodeURIComponent(userId)}`,
    { cache: "no-store" },
  );
  return parseJSONOrThrow<SpeakingSessionSummary[]>(response);
}

/**
 * GET /sessions/{id} — full breakdown for a single session. Passing userId
 * lets the backend scope the lookup to the requesting user (see Phase 0
 * report for the current, auth-less limits of that check).
 */
export async function getSpeakingSession(
  sessionId: string,
  userId?: string,
): Promise<SpeakingSessionDetail> {
  const query = userId ? `?userId=${encodeURIComponent(userId)}` : "";
  const response = await fetch(`${API_BASE}/sessions/${sessionId}${query}`, {
    cache: "no-store",
  });
  return parseJSONOrThrow<SpeakingSessionDetail>(response);
}

/** POST /sessions/{id}/share — mints (or returns the existing) public share token. */
export async function createShareLink(
  sessionId: string,
): Promise<CreateShareLinkResponse> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/share`, {
    method: "POST",
  });
  return parseJSONOrThrow<CreateShareLinkResponse>(response);
}

/** GET /sessions/public/{token} — unauthenticated read of a shared session. */
export async function getPublicSpeakingSession(
  shareToken: string,
): Promise<SpeakingSessionDetail> {
  const response = await fetch(`${API_BASE}/sessions/public/${shareToken}`, {
    cache: "no-store",
  });
  return parseJSONOrThrow<SpeakingSessionDetail>(response);
}
