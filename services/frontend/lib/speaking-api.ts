import {
  CreateShareLinkResponse,
  SpeakingSessionDetail,
  SpeakingSessionSummary,
} from "@/app/types/speaking";

// GOA-132: every browser-facing call now goes through the Gateway, which owns
// JWT validation, rate limiting, correlation IDs, and keeps INTERNAL_API_KEY
// server-side. It also sources userId from the validated token rather than from
// the caller — which is why the userId parameters these functions used to take
// are gone. The value was never the client's to supply: Speaking scoped
// /sessions/{id} to a user only when a userId query parameter was present, so
// omitting it returned any user's transcript.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/speaking`;

// Public share reads are unauthenticated by design (the recipient of a link has
// no account), so they sit outside the Gateway's /api group and must not carry
// credentials.
const PUBLIC_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/speaking`;

async function parseJSONOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(
      message || `Request failed with status ${response.status}`,
    );
  }
  return response.json();
}

/**
 * GET /api/speaking/sessions — the signed-in user's history, most recent first.
 *
 * credentials: "include" is not optional. Auth rides on an HttpOnly cookie and
 * fetch does not send cookies cross-origin by default; the frontend is :3000
 * and the Gateway is :8080, so without it every call 401s.
 */
export async function listSpeakingSessions(): Promise<SpeakingSessionSummary[]> {
  const response = await fetch(`${API_BASE}/sessions`, {
    cache: "no-store",
    credentials: "include",
  });
  return parseJSONOrThrow<SpeakingSessionSummary[]>(response);
}

/** GET /api/speaking/sessions/{id} — full breakdown, scoped to the token's user. */
export async function getSpeakingSession(
  sessionId: string,
): Promise<SpeakingSessionDetail> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    cache: "no-store",
    credentials: "include",
  });
  return parseJSONOrThrow<SpeakingSessionDetail>(response);
}

/** POST /api/speaking/sessions/{id}/share — mints (or returns) the share token. */
export async function createShareLink(
  sessionId: string,
): Promise<CreateShareLinkResponse> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/share`, {
    method: "POST",
    credentials: "include",
  });
  return parseJSONOrThrow<CreateShareLinkResponse>(response);
}

/** GET /speaking/sessions/public/{token} — unauthenticated read of a shared session. */
export async function getPublicSpeakingSession(
  shareToken: string,
): Promise<SpeakingSessionDetail> {
  const response = await fetch(`${PUBLIC_BASE}/sessions/public/${shareToken}`, {
    cache: "no-store",
  });
  return parseJSONOrThrow<SpeakingSessionDetail>(response);
}
