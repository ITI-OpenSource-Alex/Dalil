// Shared response shapes for the chat writing-practice path (lib/writing-stream.ts)
// and the exam writing path (lib/writing-exam.ts). No fetch helpers live here —
// the chat path streams over SSE (writing-stream.ts) and the exam path posts to
// /api/writing/essays/:essayId/evaluate directly; this file previously also
// exported an evaluateEssay() calling a nonexistent /api/writing/evaluate route,
// which was dead code (nothing called it) and has been removed.

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
