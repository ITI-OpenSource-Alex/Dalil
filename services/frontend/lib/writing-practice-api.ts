import { throwForResponse } from "@/lib/subscription";

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/writing`;

export interface CreateEssayResponse {
  id: number;
  status: string;
}

/**
 * POST /api/writing/essays/upload with no file -- the same route the
 * onboarding CV step's sibling (uploadCv) and Chat's classifier-driven
 * writing path both already exercise (the latter via Orchestration calling
 * the Writing service directly, not through this route). This is Practice's
 * standalone equivalent: create the essay row up front, entirely outside
 * Chat's /api/chat + intent-classification pipeline, so Writing Practice
 * doesn't depend on an LLM classifier to even start.
 *
 * RequirePaid on the Gateway (server.go) -- a free-tier caller gets a 403
 * {error: "subscription_required"}, surfaced via throwForResponse exactly
 * like every other paid route in this codebase.
 */
export async function createEssay(
  essayText: string,
  submissionType: string,
): Promise<CreateEssayResponse> {
  const form = new FormData();
  form.append("essayText", essayText);
  form.append("submissionType", submissionType);

  const response = await fetch(`${API_BASE}/essays/upload`, {
    method: "POST",
    credentials: "include",
    body: form,
  });

  if (!response.ok) {
    await throwForResponse(response, "writing-practice");
  }

  return response.json();
}
