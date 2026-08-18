import type { MotivationLetterReview } from "@/app/types/checklist";

// Through the Gateway, which injects X-User-ID from the JWT — same rationale as
// checklist-api.ts and every other client here (BUG-046): the browser never sends a
// user id or a service key.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/writing/motivation-letters`;

const fetchOptions: RequestInit = { credentials: "include" };

async function parseJSONOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json();
}

/**
 * POST /api/writing/motivation-letters
 *
 * Returns the completed review, not a job id. Five criterion agents run inside this
 * request, so it can take tens of seconds — callers should render progressive or
 * explanatory loading rather than a bare spinner.
 */
export async function reviewMotivationLetter(input: {
  content: string;
  programId?: string | null;
}): Promise<MotivationLetterReview> {
  const response = await fetch(API_BASE, {
    ...fetchOptions,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: input.content,
      programId: input.programId ?? null,
    }),
  });
  return parseJSONOrThrow<MotivationLetterReview>(response);
}

/** GET /api/writing/motivation-letters?programId= — prior reviews, newest first. */
export async function listMotivationLetters(
  programId?: string,
): Promise<
  Array<{
    letterId: number;
    programId: string | null;
    status: string;
    overallScore: number | null;
    createdAt: string | null;
  }>
> {
  const url = programId
    ? `${API_BASE}?programId=${encodeURIComponent(programId)}`
    : API_BASE;
  const response = await fetch(url, fetchOptions);
  return parseJSONOrThrow(response);
}
