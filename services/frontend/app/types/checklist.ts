// Mirrors services/rag/app/schemas/checklists.py (GOA-084 persistence + GOA-035
// financial extension), as proxied through the Gateway's /api/checklists/* routes.

export interface ChecklistItem {
  itemId: string;
  title: string;
  description: string | null;
  category: string | null;
  checked: boolean;
  // Present when the item can be actioned inside the product rather than only
  // ticked off. Derived server-side from the stable item_id, so checklists
  // generated before the feature existed carry it too.
  actionType?: string | null;
  actionTarget?: string | null;
}

export const MOTIVATION_LETTER_ACTION = "motivation_letter_review";

export interface MotivationLetterIssue {
  quote: string;
  why: string;
  suggestion: string;
}

export interface MotivationLetterCriterion {
  criterion: string;
  // null whenever the criterion abstained or errored. Never rendered as 0.
  score: number | null;
  status: "complete" | "insufficient_evidence" | "error";
  strengths: string[];
  issues: MotivationLetterIssue[];
  unaddressed_requirements?: string[];
  error?: string;
}

export interface MotivationLetterReview {
  letterId: number;
  userId: string;
  programId: string | null;
  status: string;
  // null unless at least three criteria scored — a mean of one or two is not an
  // overall judgement.
  overallScore: number | null;
  criteria: MotivationLetterCriterion[];
  programmeSnapshot: Record<string, unknown> | null;
  content: string | null;
  errorMessage: string | null;
  createdAt: string | null;
  completedAt: string | null;
}

export interface ChecklistResponse {
  checklistId: string;
  programId: string;
  programName?: string | null;
  country?: string | null;
  discipline?: string | null;
  generatedBy: "llm" | "fallback" | "requirements";
  items: ChecklistItem[];
}

export interface FinancialRequirementItem {
  type: string;
  country: string;
  issuingBody: string;
  message: string;
  sourceUrl: string | null;
  lastVerifiedAt: string | null;
}

export interface FinancialRequirementsResponse {
  programId: string;
  items: FinancialRequirementItem[];
}

// The five phases GOA-035 requires. The backend (GOA-084) has no phase field on a
// checklist item yet — only a free-text `category` the LLM assigns itself — so
// PHASE_ORDER plus lib/checklist-phases.ts's mapping is a frontend-only, best-effort
// grouping until that field exists. Financial Requirements is deliberately never
// populated from this mapping: it is rendered exclusively from
// FinancialRequirementsResponse (see components/checklist/FinancialRequirements.tsx).
export type Phase =
  | "Language Prep"
  | "Documents"
  | "Application"
  | "Financial Requirements"
  | "Post-acceptance";

export const PHASE_ORDER: Phase[] = [
  "Language Prep",
  "Documents",
  "Application",
  "Financial Requirements",
  "Post-acceptance",
];
