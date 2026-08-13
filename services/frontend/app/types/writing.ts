/** One row of GET /api/writing/essays -- a summary, not the full essay text
 * or evaluation. Mirrors the Writing service's EssayHistoryItem schema
 * (services/writing/app/schemas.py). There is no per-essay detail endpoint
 * yet, so the history list is the whole UI for now -- see
 * lib/writing-history-api.ts. */
export interface EssayHistoryItem {
  id: number;
  submitted_at: string;
  status: string;
  submission_type: string | null;
  exam_type: string | null;
  task_number: number | null;
  overall_band: number | null;
  excerpt: string;
}
