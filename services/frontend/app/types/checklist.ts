// Mirrors services/rag/app/schemas/checklists.py (GOA-084 persistence + GOA-035
// financial extension), as proxied through the Gateway's /api/checklists/* routes.

export interface ChecklistItem {
  itemId: string;
  title: string;
  description: string | null;
  category: string | null;
  checked: boolean;
}

export interface ChecklistResponse {
  checklistId: string;
  programId: string;
  generatedBy: "llm" | "fallback";
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
