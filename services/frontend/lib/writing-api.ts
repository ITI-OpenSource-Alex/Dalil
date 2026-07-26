// The Writing service listens on 8000 (see docker-compose.yml). The previous
// fallback of 8001 pointed at nothing at all, so a developer without a .env file
// got connection failures rather than a clear "you are misconfigured" — and no
// .env.example existed to copy from (BUG-045).
const API_BASE =
  process.env.NEXT_PUBLIC_WRITING_API_URL ?? "http://localhost:8000";

const headers = {
  "Content-Type": "application/json",
  "x-internal-api-key": process.env.NEXT_PUBLIC_INTERNAL_API_KEY ?? "",
};

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
  const response = await fetch(`${API_BASE}/writing/evaluate`, {
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
    throw new Error(await response.text());
  }

  return response.json();
}
