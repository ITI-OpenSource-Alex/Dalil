import { throwForResponse } from "@/lib/subscription";

// Writing is reached through the Gateway, not directly on :8000 — same reason as
// exam-api.ts: calling the service directly published INTERNAL_API_KEY to every
// browser via a NEXT_PUBLIC_ variable (BUG-046).
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/writing`;

const headers = {
  "Content-Type": "application/json",
};

const fetchOptions: RequestInit = { credentials: "include" };

export interface HighlightedIssue {
  text: string;
  issue: string;
  suggestion: string;
  start: number;
  end: number;
}

export interface CriterionEvaluation {
  criterion: "task_response" | "cohesion" | "vocabulary" | "grammar";

  band_score: number;
  feedback: string;
  highlighted_issues: HighlightedIssue[];
}

export interface EssayEvaluationResponse {
  essay_id: number;
  evaluations: CriterionEvaluation[];
  overall_band: number;
  from_cache: boolean;
}

export async function evaluateEssay(
  userId: string,
  essayText: string,
  submissionType: string,
  examType: string,
): Promise<EssayEvaluationResponse> {
  const response = await fetch(`${API_BASE}/evaluate`, {
    ...fetchOptions,
    method: "POST",
    headers,
    body: JSON.stringify({
      userId,
      essayText,
      submissionType,
      examType,
    }),
  });

  if (!response.ok) {
    await throwForResponse(response, "essay-evaluation");
  }

  return response.json();
}
