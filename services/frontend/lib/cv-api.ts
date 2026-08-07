import { throwForResponse } from "@/lib/subscription";
import { SSEParser } from "@/lib/chat-stream";

// Same reasoning as speaking-api.ts / writing-history-api.ts: every
// browser-facing call goes through the Gateway, which owns JWT validation and
// sources the user id from the validated token, never a caller-supplied one.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/writing/cv`;

const fetchOptions: RequestInit = { credentials: "include" };

export interface CvUploadResponse {
  cvId: number;
  status: string;
  s3Key: string;
}

/** GET /api/writing/cv/latest -- the signed-in user's most recent upload. */
export interface CvLatestResponse {
  cvId: number;
  s3Key: string;
  originalFilename: string;
  status: "processing" | "ready" | "failed" | string;
  uploadedAt: string;
  errorMessage?: string | null;
}

/**
 * GET /api/writing/cv/latest. Returns null rather than throwing on a 404 --
 * "no CV uploaded yet" is an expected first-visit state for this page, not a
 * fault the caller needs to branch on with try/catch.
 */
export async function getLatestCv(): Promise<CvLatestResponse | null> {
  const response = await fetch(`${API_BASE}/latest`, {
    ...fetchOptions,
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

/**
 * POST /api/writing/cv/upload.
 *
 * Free-tier as of Phase E (docs/IA-REDESIGN-PROPOSAL.md): a Free user can
 * upload and hold a CV, they just cannot ask for an AI review of it. A 403
 * here is therefore a real fault, not a paywall -- unlike streamCvReview
 * below, this deliberately does not pass a PaidFeatureId to throwForResponse.
 */
export async function uploadCv(file: File): Promise<CvUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/upload`, {
    ...fetchOptions,
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

export interface CvReviewSection {
  name: string;
  score: number;
  issues: string[];
  suggestions: string[];
}

export type CvSectionEvent = { type: "section" } & CvReviewSection;

export type CvCompleteEvent = {
  type: "complete";
  overallScore: number;
  sections: CvReviewSection[];
  fromCache?: boolean;
};

export type CvErrorEvent = { type: "error"; detail: string };

export type CvReviewEvent = CvSectionEvent | CvCompleteEvent | CvErrorEvent;

/**
 * POST /api/writing/cv/review, streamed via SSE. Uses the same shared frame
 * reassembly as lib/writing-stream.ts and lib/chat-stream.ts (buffering, the
 * CRLF fix, the trailing-frame flush), but this endpoint's frames put the
 * event's kind in the `event:` line ("section" / "complete" / "error")
 * rather than embedding a `type` field in the JSON body the way chat's and
 * writing's frames do -- so its `parse` callback folds the two back together.
 */
export async function streamCvReview(
  params: { cvS3Key: string; targetCountry: string; targetField: string },
  onEvent: (event: CvReviewEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/review`, {
    ...fetchOptions,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    await throwForResponse(response, "cv-review");
  }

  if (!response.body) {
    throw new Error("Missing SSE response body.");
  }

  const parser = new SSEParser<CvReviewEvent>(({ eventName, data }) => {
    if (!eventName || typeof data !== "object" || data === null) return null;
    return { type: eventName, ...data } as CvReviewEvent;
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    parser.push(chunk).forEach(onEvent);
  }

  parser.flush().forEach(onEvent);
}
