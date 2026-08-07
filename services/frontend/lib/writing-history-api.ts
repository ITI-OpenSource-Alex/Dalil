import { EssayHistoryItem } from "@/app/types/writing";
import { dedupe } from "@/lib/request-dedupe";

// Same reasoning as speaking-api.ts: every browser-facing call goes through
// the Gateway, which owns JWT validation, rate limiting and correlation IDs,
// and sources the user id from the validated token rather than a caller-
// supplied parameter.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/writing`;

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
 * GET /api/writing/essays -- the signed-in user's own essays (chat practice
 * submissions and exam task submissions alike), most recent first, 20 per
 * page. Added in Phase B (services/writing/app/routers/essays.py); this is
 * its first browser-facing consumer.
 */
export async function listEssays(
  options: { page?: number; submissionType?: string } = {},
): Promise<EssayHistoryItem[]> {
  const params = new URLSearchParams();
  if (options.page) params.set("page", String(options.page));
  if (options.submissionType) params.set("submission_type", options.submissionType);
  const query = params.toString();
  const url = `${API_BASE}/essays${query ? `?${query}` : ""}`;

  return dedupe(`GET ${url}`, async () => {
    const response = await fetch(url, {
      cache: "no-store",
      credentials: "include",
    });
    return parseJSONOrThrow<EssayHistoryItem[]>(response);
  });
}
